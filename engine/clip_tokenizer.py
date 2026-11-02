"""
engine/clip_tokenizer.py — Pure Python / NumPy CLIP SimpleTokenizer.

Zero PyTorch, zero Torchvision dependency.
Provides exact numerical equivalence with OpenAI CLIP and OpenCLIP SimpleTokenizer.
Loads vocabulary from models/clip/bpe_simple_vocab_16e6.txt.gz.
"""

import gzip
import html
import os
import sys
import string
from functools import lru_cache
from pathlib import Path
from typing import List, Tuple, Dict, Set, Optional

import ftfy
import numpy as np
import regex as re

def resolve_bpe_path(custom_path: Optional[Path] = None) -> Path:
    """Robustly resolve path to bpe_simple_vocab_16e6.txt.gz across frozen, dev and custom paths."""
    if custom_path and Path(custom_path).exists():
        return Path(custom_path)
    if "RENDERFLOW_BPE_PATH" in os.environ:
        p = Path(os.environ["RENDERFLOW_BPE_PATH"])
        if p.exists():
            return p
    if getattr(sys, "frozen", False):
        exe_parent = Path(sys.executable).resolve().parent
        for cand in [
            exe_parent / "models" / "clip" / "bpe_simple_vocab_16e6.txt.gz",
            exe_parent / "_internal" / "models" / "clip" / "bpe_simple_vocab_16e6.txt.gz",
        ]:
            if cand.exists():
                return cand
    root = Path(__file__).resolve().parent.parent
    for cand in [
        root / "models" / "clip" / "bpe_simple_vocab_16e6.txt.gz",
        root.parent / "models" / "clip" / "bpe_simple_vocab_16e6.txt.gz",
        Path.cwd() / "models" / "clip" / "bpe_simple_vocab_16e6.txt.gz",
    ]:
        if cand.exists():
            return cand
    # Fallback to site-packages if open_clip is installed
    try:
        import open_clip.tokenizer as oct
        default_bpe = Path(oct.default_bpe())
        if default_bpe.exists():
            return default_bpe
    except Exception:
        pass
    return root / "models" / "clip" / "bpe_simple_vocab_16e6.txt.gz"

DEFAULT_BPE_PATH = resolve_bpe_path()


@lru_cache()
def bytes_to_unicode() -> Dict[int, str]:
    bs = (
        list(range(ord("!"), ord("~") + 1))
        + list(range(ord("¡"), ord("¬") + 1))
        + list(range(ord("®"), ord("ÿ") + 1))
    )
    cs = bs[:]
    n = 0
    for b in range(2**8):
        if b not in bs:
            bs.append(b)
            cs.append(2**8 + n)
            n += 1
    cs = [chr(n) for n in cs]
    return dict(zip(bs, cs))


def get_pairs(word: Tuple[str, ...]) -> Set[Tuple[str, str]]:
    pairs = set()
    prev_char = word[0]
    for char in word[1:]:
        pairs.add((prev_char, char))
        prev_char = char
    return pairs


def basic_clean(text: str) -> str:
    text = ftfy.fix_text(text)
    text = html.unescape(html.unescape(text))
    return text.strip()


def whitespace_clean(text: str) -> str:
    return " ".join(text.split()).strip()


def clean_lower(text: str) -> str:
    return whitespace_clean(basic_clean(text)).lower()


class SimpleTokenizer:
    """
    Pure Python implementation of CLIP byte-pair encoding (BPE) tokenizer.
    Guarantees zero Torch / Torchvision dependencies.
    """
    def __init__(self, bpe_path: Optional[Path] = None):
        target_path = resolve_bpe_path(bpe_path)
        if not target_path.exists():
            raise FileNotFoundError(f"CLIP BPE vocabulary file not found at {target_path}")

        self.byte_encoder = bytes_to_unicode()
        self.byte_decoder = {v: k for k, v in self.byte_encoder.items()}

        with gzip.open(target_path, "rt", encoding="utf-8") as f:
            merges = f.read().split("\n")
        merges = merges[1 : 49152 - 256 - 2 + 1]
        merges = [tuple(merge.split()) for merge in merges]

        vocab = list(bytes_to_unicode().values())
        vocab = vocab + [v + "</w>" for v in vocab]
        for merge in merges:
            vocab.append("".join(merge))

        special_tokens = ["<start_of_text>", "<end_of_text>"]
        vocab.extend(special_tokens)

        self.encoder = dict(zip(vocab, range(len(vocab))))
        self.decoder = {v: k for k, v in self.encoder.items()}
        self.bpe_ranks = dict(zip(merges, range(len(merges))))
        self.cache = {t: t for t in special_tokens}
        special = "|".join(special_tokens)
        self.pat = re.compile(
            special + r"""|'s|'t|'re|'ve|'m|'ll|'d|[\p{L}]+|[\p{N}]|[^\s\p{L}\p{N}]+""",
            re.IGNORECASE,
        )
        self.vocab_size = len(self.encoder)
        self.sot_token_id = self.encoder["<start_of_text>"]
        self.eot_token_id = self.encoder["<end_of_text>"]

    def bpe(self, token: str) -> str:
        if token in self.cache:
            return self.cache[token]
        word = tuple(token[:-1]) + (token[-1] + "</w>",)
        pairs = get_pairs(word)
        if not pairs:
            return token + "</w>"

        while True:
            bigram = min(pairs, key=lambda pair: self.bpe_ranks.get(pair, float("inf")))
            if bigram not in self.bpe_ranks:
                break
            first, second = bigram
            new_word = []
            i = 0
            while i < len(word):
                try:
                    j = word.index(first, i)
                    new_word.extend(word[i:j])
                    i = j
                except Exception:
                    new_word.extend(word[i:])
                    break

                if word[i] == first and i < len(word) - 1 and word[i + 1] == second:
                    new_word.append(first + second)
                    i += 2
                else:
                    new_word.append(word[i])
                    i += 1
            new_word = tuple(new_word)
            word = new_word
            if len(word) == 1:
                break
            else:
                pairs = get_pairs(word)
        word = " ".join(word)
        self.cache[token] = word
        return word

    def encode(self, text: str) -> List[int]:
        bpe_tokens = []
        text = clean_lower(text)
        for token in re.findall(self.pat, text):
            token = "".join(self.byte_encoder[b] for b in token.encode("utf-8"))
            bpe_tokens.extend(self.encoder[bpe_token] for bpe_token in self.bpe(token).split(" "))
        return bpe_tokens

    def decode(self, tokens: List[int]) -> str:
        text = "".join([self.decoder[token] for token in tokens])
        text = (
            bytearray([self.byte_decoder[c] for c in text])
            .decode("utf-8", errors="replace")
            .replace("</w>", " ")
        )
        return text

