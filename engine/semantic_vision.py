#!/usr/bin/env python3
"""
engine/semantic_vision.py — Vision-Language Semantic Intelligence Engine for RenderFlow.

v2.6 Dual-Provider Architecture:
1. Primary Provider: ONNX Runtime CPU FP32 (pure CPUExecutionProvider, 4 threads).
   - Zero CUDA / GPU dependency, fully air-gapped and offline.
   - Ultra-low memory working set (~595 MB total session RAM).
   - Instant import (0.55s) with pure PIL/NumPy preprocessing & SimpleTokenizer.
2. Fallback Provider: PyTorch OpenCLIP ViT-B/32 CPU (models/clip/ViT-B-32-state-dict.pt).
   - Automatic fallback when ONNX models are missing or in AUTO mode.
3. Provider Selection Modes:
   - "auto" (default): Prefers ONNX FP32; gracefully falls back to PyTorch with logged warning.
   - "onnx": Strictly enforces ONNX CPU execution; reports unavailable if missing.
   - "pytorch": Explicitly selects legacy PyTorch engine.
   - Configurable via argument or RENDERFLOW_SEMANTIC_PROVIDER environment variable.
4. Content-hash addressed disk caching (SHA-256) for sub-millisecond retrieval.
5. Multi-prompt contextual expansion for abstract and metaphorical scene understanding.
6. Deterministic, testable fallback if neural inference is disabled or unavailable.
"""

import os
import sys
import json
import time
import hashlib
import logging
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Union
import numpy as np
from PIL import Image

logger = logging.getLogger("rendering_studio.semantic_vision")

ROOT_DIR = Path(__file__).resolve().parent.parent

def resolve_clip_model_path(filename: str) -> Path:
    """Robustly resolve path to clip models across frozen, dev and custom paths."""
    if getattr(sys, "frozen", False):
        exe_parent = Path(sys.executable).resolve().parent
        for cand in [
            exe_parent / "models" / "clip" / filename,
            exe_parent / "_internal" / "models" / "clip" / filename,
        ]:
            if cand.exists():
                return cand
    if "RENDERFLOW_MODELS_DIR" in os.environ:
        p = Path(os.environ["RENDERFLOW_MODELS_DIR"]) / "clip" / filename
        if p.exists():
            return p
    root = ROOT_DIR
    for cand in [
        root / "models" / "clip" / filename,
        root.parent / "models" / "clip" / filename,
        Path.cwd() / "models" / "clip" / filename,
    ]:
        if cand.exists():
            return cand
    return root / "models" / "clip" / filename

MODEL_WEIGHTS_PATH = resolve_clip_model_path("ViT-B-32-state-dict.pt")
DEFAULT_ONNX_VISUAL_PATH = resolve_clip_model_path("visual_fp32.onnx")
DEFAULT_ONNX_TEXT_PATH = resolve_clip_model_path("text_fp32.onnx")

CACHE_DIR = ROOT_DIR / ".cache" / "image_sync_v3"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
CACHE_FILE = CACHE_DIR / "clip_embeddings_cache.json"

MODEL_IDENTIFIER = "open_clip_vit_b_32_v1"
EMBEDDING_DIM = 512

CLIP_MEAN = np.array([0.48145466, 0.4578275, 0.40821073], dtype=np.float32)
CLIP_STD = np.array([0.26862954, 0.26130258, 0.27577711], dtype=np.float32)


class SemanticProviderMode(str, Enum):
    AUTO = "auto"
    ONNX = "onnx"
    PYTORCH = "pytorch"


def pil_preprocess(pil_img: Image.Image) -> np.ndarray:
    """
    Pure PIL and NumPy image preprocessing matching Torchvision Bicubic Antialiased Resize + CenterCrop.
    Produces float32 array in NCHW format [1, 3, 224, 224] with zero PyTorch / Torchvision dependency.
    """
    w, h = pil_img.size
    if w <= h:
        ow = 224
        oh = int(224 * h / w)
    else:
        oh = 224
        ow = int(224 * w / h)
    resized = pil_img.resize((ow, oh), resample=Image.Resampling.BICUBIC)
    crop_top = int(round((oh - 224) / 2.0))
    crop_left = int(round((ow - 224) / 2.0))
    cropped = resized.crop((crop_left, crop_top, crop_left + 224, crop_top + 224))
    arr = np.array(cropped, dtype=np.float32) / 255.0
    norm = (arr - CLIP_MEAN) / CLIP_STD
    return np.transpose(norm, (2, 0, 1))


class ONNXRuntimeProvider:
    """
    Primary Semantic Provider: ONNX Runtime CPU FP32.
    Runs standalone visual and text ONNX graphs on CPU with 4 intra-op threads.
    """
    def __init__(
        self,
        visual_path: Path,
        text_path: Path,
        num_threads: int = 4
    ):
        self.visual_path = Path(visual_path)
        self.text_path = Path(text_path)
        self.num_threads = num_threads
        self.active_provider = "onnx"
        self.execution_provider = "CPUExecutionProvider"

        if not self.visual_path.exists():
            raise FileNotFoundError(f"ONNX visual model not found at {self.visual_path}")
        if not self.text_path.exists():
            raise FileNotFoundError(f"ONNX text model not found at {self.text_path}")

        import onnxruntime as ort
        try:
            from engine.clip_tokenizer import SimpleTokenizer
        except (ModuleNotFoundError, ImportError):
            try:
                from clip_tokenizer import SimpleTokenizer
            except (ModuleNotFoundError, ImportError):
                from open_clip.tokenizer import SimpleTokenizer

        self._tokenizer = SimpleTokenizer()
        self._sot_token = self._tokenizer.encoder["<start_of_text>"]
        self._eot_token = self._tokenizer.encoder["<end_of_text>"]

        sess_opts = ort.SessionOptions()
        sess_opts.intra_op_num_threads = self.num_threads
        sess_opts.inter_op_num_threads = 1
        sess_opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        sess_opts.enable_cpu_mem_arena = True

        t0 = time.time()
        self._vis_session = ort.InferenceSession(
            str(self.visual_path), sess_opts, providers=["CPUExecutionProvider"]
        )
        self._txt_session = ort.InferenceSession(
            str(self.text_path), sess_opts, providers=["CPUExecutionProvider"]
        )
        t_load = time.time() - t0
        logger.info(
            f"ONNX Runtime CPU FP32 initialized in {t_load:.2f}s "
            f"(threads: {self.num_threads}, provider: CPUExecutionProvider)"
        )

    @property
    def is_available(self) -> bool:
        return self._vis_session is not None and self._txt_session is not None

    def tokenize(self, texts: List[str], context_length: int = 77) -> np.ndarray:
        """Pure NumPy tokenization matching OpenCLIP SimpleTokenizer."""
        res = np.zeros((len(texts), context_length), dtype=np.int64)
        for i, t in enumerate(texts):
            clean_text = t.strip() if t.strip() else ""
            tokens = [self._sot_token] + self._tokenizer.encode(clean_text)[:context_length - 2] + [self._eot_token]
            res[i, :len(tokens)] = tokens
        return res

    def encode_images(self, pil_images: List[Image.Image]) -> np.ndarray:
        """Run batch visual inference on CPU. Returns normalized 512-dim float32 array."""
        if not pil_images:
            return np.zeros((0, EMBEDDING_DIM), dtype=np.float32)
        batch_arr = np.stack([pil_preprocess(im) for im in pil_images], axis=0)
        outputs = self._vis_session.run(None, {"image": batch_arr})[0]
        # Guarantee strict L2 normalization
        norms = np.linalg.norm(outputs, axis=-1, keepdims=True)
        norms[norms == 0] = 1.0
        return (outputs / norms).astype(np.float32)

    def encode_texts(self, texts: List[str]) -> np.ndarray:
        """Run batch text inference on CPU. Returns normalized 512-dim float32 array."""
        if not texts:
            return np.zeros((0, EMBEDDING_DIM), dtype=np.float32)
        tokens_arr = self.tokenize(texts)
        outputs = self._txt_session.run(None, {"text": tokens_arr})[0]
        # Guarantee strict L2 normalization
        norms = np.linalg.norm(outputs, axis=-1, keepdims=True)
        norms[norms == 0] = 1.0
        return (outputs / norms).astype(np.float32)


class PyTorchProvider:
    """
    Fallback Semantic Provider: PyTorch OpenCLIP ViT-B/32 CPU.
    Loads models/clip/ViT-B-32-state-dict.pt on CPU.
    """
    def __init__(self, weights_path: Path):
        self.weights_path = Path(weights_path)
        self.active_provider = "pytorch"
        self.execution_provider = "PyTorch ATen CPU"

        if not self.weights_path.exists():
            raise FileNotFoundError(f"PyTorch model weights not found at {self.weights_path}")

        import torch
        import open_clip

        t0 = time.time()
        logger.info(f"Loading Fallback PyTorch OpenCLIP model from {self.weights_path}...")
        sd = torch.load(str(self.weights_path), map_location="cpu", weights_only=True)

        root_logger = logging.getLogger()
        old_level = root_logger.level
        root_logger.setLevel(logging.ERROR)
        try:
            model, _, preprocess = open_clip.create_model_and_transforms("ViT-B-32", pretrained=None)
        finally:
            root_logger.setLevel(old_level)

        model.load_state_dict(sd, strict=False)
        model.eval()

        self._model = model
        self._preprocess = preprocess
        self._tokenizer = open_clip.get_tokenizer("ViT-B-32")
        logger.info(f"Fallback PyTorch model loaded in {time.time()-t0:.2f}s.")

    @property
    def is_available(self) -> bool:
        return self._model is not None

    def encode_images(self, pil_images: List[Image.Image]) -> np.ndarray:
        import torch
        if not pil_images:
            return np.zeros((0, EMBEDDING_DIM), dtype=np.float32)
        tensors = [self._preprocess(im) for im in pil_images]
        batch_t = torch.stack(tensors)
        with torch.no_grad():
            feat = self._model.encode_image(batch_t, normalize=True)
            return feat.cpu().numpy().astype(np.float32)

    def encode_texts(self, texts: List[str]) -> np.ndarray:
        import torch
        if not texts:
            return np.zeros((0, EMBEDDING_DIM), dtype=np.float32)
        tokens = self._tokenizer(texts)
        with torch.no_grad():
            feat = self._model.encode_text(tokens, normalize=True)
            return feat.cpu().numpy().astype(np.float32)


class SemanticVisionModel:
    """
    Singleton Manager for local neural cross-modal vision-language intelligence.
    Supports ONNX Runtime CPU FP32 primary execution with transparent PyTorch fallback.
    """
    _instance: Optional["SemanticVisionModel"] = None
    _is_initialized: bool = False
    _provider = None
    _load_failed: bool = False
    _fail_reason: str = ""

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(SemanticVisionModel, cls).__new__(cls)
        return cls._instance

    @classmethod
    def reset_instance(cls):
        """Reset the singleton instance (primarily for isolated test harnesses)."""
        cls._instance = None
        cls._is_initialized = False

    def __init__(
        self,
        weights_path: Optional[Path] = None,
        cache_path: Optional[Path] = None,
        provider_mode: Optional[Union[str, SemanticProviderMode]] = None,
        visual_model_path: Optional[Path] = None,
        text_model_path: Optional[Path] = None,
        num_threads: int = 4
    ):
        if self._is_initialized:
            return

        self.weights_path = Path(weights_path) if weights_path else MODEL_WEIGHTS_PATH
        self.visual_model_path = Path(visual_model_path) if visual_model_path else DEFAULT_ONNX_VISUAL_PATH
        self.text_model_path = Path(text_model_path) if text_model_path else DEFAULT_ONNX_TEXT_PATH
        self.cache_path = Path(cache_path) if cache_path else CACHE_FILE
        self.num_threads = num_threads
        self.device = "cpu"

        # Resolve provider mode
        if isinstance(provider_mode, SemanticProviderMode):
            self.provider_mode = provider_mode
        else:
            raw_mode = (
                str(provider_mode.value if hasattr(provider_mode, 'value') else provider_mode)
                if provider_mode is not None
                else os.environ.get("RENDERFLOW_SEMANTIC_PROVIDER", "auto")
            ).strip().lower()

            try:
                self.provider_mode = SemanticProviderMode(raw_mode)
            except ValueError:
                logger.warning(f"Unknown provider mode '{raw_mode}'. Defaulting to 'auto'.")
                self.provider_mode = SemanticProviderMode.AUTO

        self.active_provider: str = "none"
        self.execution_provider: str = "none"
        self._cache: Dict[str, List[float]] = self._load_cache()
        self._text_cache: Dict[str, np.ndarray] = {}

        self._init_provider()
        self._is_initialized = True

    def _load_cache(self) -> Dict[str, List[float]]:
        if self.cache_path.exists():
            try:
                with open(self.cache_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to read semantic vision cache: {e}")
        return {}

    def _save_cache(self):
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.cache_path, "w", encoding="utf-8") as f:
                json.dump(self._cache, f)
        except Exception as e:
            logger.warning(f"Failed to save semantic vision cache: {e}")

    def _init_provider(self):
        """Initialize the active provider according to configured provider_mode."""
        self._load_failed = False
        self._fail_reason = ""

        # Mode: Explicit PyTorch
        if self.provider_mode == SemanticProviderMode.PYTORCH:
            try:
                self._provider = PyTorchProvider(self.weights_path)
                self.active_provider = "pytorch"
                self.execution_provider = self._provider.execution_provider
                logger.info("Initialized Explicit Semantic Provider: PyTorch OpenCLIP ViT-B/32 CPU")
                return
            except Exception as e:
                self._load_failed = True
                self._fail_reason = f"Explicit PyTorch initialization failed: {e}"
                self.active_provider = "none"
                self.execution_provider = "none"
                logger.error(self._fail_reason)
                return

        # Mode: Explicit ONNX
        if self.provider_mode == SemanticProviderMode.ONNX:
            try:
                self._provider = ONNXRuntimeProvider(
                    visual_path=self.visual_model_path,
                    text_path=self.text_model_path,
                    num_threads=self.num_threads
                )
                self.active_provider = "onnx"
                self.execution_provider = self._provider.execution_provider
                logger.info(
                    f"Initialized Explicit Semantic Provider: ONNX Runtime CPU "
                    f"({self.num_threads} threads, CPUExecutionProvider)"
                )
                return
            except Exception as e:
                self._load_failed = True
                self._fail_reason = f"Explicit ONNX initialization failed: {e}"
                self.active_provider = "none"
                self.execution_provider = "none"
                logger.error(self._fail_reason)
                return

        # Mode: AUTO (Primary ONNX with automatic PyTorch fallback)
        try:
            self._provider = ONNXRuntimeProvider(
                visual_path=self.visual_model_path,
                text_path=self.text_model_path,
                num_threads=self.num_threads
            )
            self.active_provider = "onnx"
            self.execution_provider = self._provider.execution_provider
            logger.info(
                f"Initialized Primary Semantic Provider: ONNX Runtime CPU "
                f"({self.num_threads} threads, CPUExecutionProvider)"
            )
            return
        except Exception as onnx_err:
            logger.warning(
                f"Primary ONNX provider unavailable or failed to initialize ({onnx_err}). "
                f"Attempting fallback to PyTorch OpenCLIP ViT-B/32..."
            )

        # Fallback to PyTorch
        try:
            self._provider = PyTorchProvider(self.weights_path)
            self.active_provider = "pytorch"
            self.execution_provider = self._provider.execution_provider
            logger.info("Initialized Fallback Semantic Provider: PyTorch OpenCLIP ViT-B/32 CPU")
            return
        except Exception as pt_err:
            self._load_failed = True
            self._fail_reason = f"Both ONNX and PyTorch providers failed to initialize (PyTorch: {pt_err})"
            self.active_provider = "none"
            self.execution_provider = "none"
            logger.error(self._fail_reason)

    @property
    def is_available(self) -> bool:
        return (not self._load_failed) and (self._provider is not None) and self._provider.is_available

    @property
    def _model(self):
        """Backward-compatibility probe for legacy inspection."""
        return getattr(self._provider, "_model", None)

    @property
    def _preprocess(self):
        """Backward-compatibility probe for legacy inspection."""
        return getattr(self._provider, "_preprocess", None)

    @property
    def _tokenizer(self):
        """Backward-compatibility probe for legacy inspection."""
        return getattr(self._provider, "_tokenizer", None)

    @staticmethod
    def compute_sha256(filepath: Path) -> str:
        hasher = hashlib.sha256()
        with open(filepath, "rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
        return hasher.hexdigest()

    def encode_text(self, text: Union[str, List[str]], contextual_expansion: bool = False) -> np.ndarray:
        """
        Encode narration text into a 512-dim L2-normalized float32 vector.
        Supports multi-prompt contextual expansion for abstract and metaphorical scenes.
        Uses in-memory cache to guarantee zero redundant neural forward passes.
        """
        cache_key = None
        if isinstance(text, str):
            cache_key = f"{text.strip()}::exp={contextual_expansion}"
            if cache_key in self._text_cache:
                return self._text_cache[cache_key].copy()
            text_queries = [text.strip()]
            if contextual_expansion and len(text.strip()) > 3:
                clean_t = text.strip().rstrip(".!?")
                text_queries.append(f"a photo showing {clean_t}")
                text_queries.append(f"a cinematic visual depicting {clean_t}")
        else:
            text_queries = list(text)

        if not text_queries:
            return np.zeros(EMBEDDING_DIM, dtype=np.float32)

        if not self.is_available:
            return self._deterministic_fallback_vector(text_queries[0])

        try:
            embs = self._provider.encode_texts(text_queries)
            # Average prompt ensemble if multiple prompts were generated via contextual expansion
            mean_feature = np.mean(embs, axis=0)
            norm = float(np.linalg.norm(mean_feature))
            if norm > 1e-9:
                mean_feature /= norm
            res = mean_feature.astype(np.float32)
            if cache_key:
                self._text_cache[cache_key] = res
            return res
        except Exception as e:
            logger.warning(f"Neural text encoding failed ({e}). Using deterministic fallback.")
            return self._deterministic_fallback_vector(text_queries[0])

    def batch_encode_texts(self, texts: List[str]) -> np.ndarray:
        """Encode a list of narration texts in a single vectorized forward pass on CPU."""
        if not texts:
            return np.zeros((0, EMBEDDING_DIM), dtype=np.float32)

        clean_texts = [t.strip() if t.strip() else "visual scene" for t in texts]

        if not self.is_available:
            return np.array([self._deterministic_fallback_vector(t) for t in clean_texts], dtype=np.float32)

        try:
            res = self._provider.encode_texts(clean_texts)
            for t, emb in zip(clean_texts, res):
                self._text_cache[t] = emb
            return res
        except Exception as e:
            logger.warning(f"Batch neural text encoding failed ({e}). Using deterministic fallback.")
            return np.array([self._deterministic_fallback_vector(t) for t in clean_texts], dtype=np.float32)

    def encode_image(self, image_or_path: Union[str, Path, Image.Image]) -> np.ndarray:
        """
        Encode an image into a 512-dim L2-normalized float32 vector.
        Uses SHA-256 disk cache for instant sub-millisecond retrieval on previously seen images.
        """
        img_obj: Optional[Image.Image] = None
        content_hash: Optional[str] = None

        if isinstance(image_or_path, (str, Path)):
            p = Path(image_or_path).resolve()
            if not p.exists():
                raise FileNotFoundError(f"Image not found for embedding: {p}")
            content_hash = self.compute_sha256(p)
            cache_key = f"{content_hash}_{MODEL_IDENTIFIER}"
            if cache_key in self._cache:
                return np.array(self._cache[cache_key], dtype=np.float32)
            try:
                img_obj = Image.open(p).convert("RGB")
            except Exception as e:
                logger.error(f"Cannot decode image {p}: {e}")
                return np.zeros(EMBEDDING_DIM, dtype=np.float32)
        elif isinstance(image_or_path, Image.Image):
            img_obj = image_or_path.convert("RGB")
        else:
            raise TypeError(f"Unsupported image type: {type(image_or_path)}")

        if not self.is_available:
            return self._deterministic_fallback_image(img_obj)

        try:
            embs = self._provider.encode_images([img_obj])
            emb = embs[0].astype(np.float32)

            if content_hash:
                cache_key = f"{content_hash}_{MODEL_IDENTIFIER}"
                self._cache[cache_key] = [round(float(x), 6) for x in emb.tolist()]
                if len(self._cache) % 5 == 0:
                    self._save_cache()

            return emb
        except Exception as e:
            logger.warning(f"Neural image encoding failed ({e}). Using fallback.")
            return self._deterministic_fallback_image(img_obj)

    def compute_similarity(self, text_emb: np.ndarray, img_emb: np.ndarray) -> float:
        """
        Compute cosine similarity between normalized text and image embeddings.
        Returns score mapped to [0.0, 1.0].
        """
        if text_emb is None or img_emb is None:
            return 0.0
        dot = float(np.dot(text_emb, img_emb))
        return max(0.0, min(1.0, dot))

    def batch_encode_images(self, image_paths: List[Path]) -> Dict[str, np.ndarray]:
        """Encode a directory or batch of image paths, leveraging disk cache."""
        embeddings = {}
        for p in image_paths:
            p = Path(p)
            try:
                embeddings[p.name] = self.encode_image(p)
            except Exception as e:
                logger.warning(f"Failed to encode {p.name}: {e}")
                embeddings[p.name] = np.zeros(EMBEDDING_DIM, dtype=np.float32)
        self._save_cache()
        return embeddings

    def _deterministic_fallback_vector(self, text: str) -> np.ndarray:
        """Safe offline fallback vector (256-dim expanded to 512-dim)."""
        vec = np.zeros(EMBEDDING_DIM, dtype=np.float32)
        words = [w.lower() for w in text.split() if len(w) >= 3]
        for w in words:
            h = int(hashlib.sha256(w.encode("utf-8")).hexdigest(), 16)
            idx = h % EMBEDDING_DIM
            sign = 1.0 if (h >> 8) & 1 else -1.0
            vec[idx] += sign
        norm = np.linalg.norm(vec)
        if norm > 1e-9:
            vec /= norm
        return vec

    def _deterministic_fallback_image(self, img: Image.Image) -> np.ndarray:
        """Safe offline image vector derived from spatial thumbnails."""
        thumb = img.resize((16, 16), Image.Resampling.BILINEAR)
        arr = np.array(thumb, dtype=np.float32).flatten()
        vec = np.zeros(EMBEDDING_DIM, dtype=np.float32)
        half = min(len(arr), EMBEDDING_DIM)
        vec[:half] = arr[:half] / 255.0
        norm = np.linalg.norm(vec)
        if norm > 1e-9:
            vec /= norm
        return vec
