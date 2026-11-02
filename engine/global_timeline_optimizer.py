#!/usr/bin/env python3
"""
engine/global_timeline_optimizer.py — Global Bipartite Timeline Optimizer.

Optimizes image assignments across the entire video timeline:
1. Global Hungarian / Auction bipartite matching over full timeline cost matrix.
2. Hard preservation of user-locked overrides (never discarded).
3. Visual continuity and smart reuse penalties (penalizes consecutive duplicates).
4. Explicit low-confidence detection and No-Match / Manual-Review outcome.
5. Calibrated evidence scores with full decision trace.
"""

import math
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any, Set
import numpy as np

logger = logging.getLogger("rendering_studio.timeline_optimizer")

# Calibrated thresholds for OpenCLIP ViT-B/32 cosine similarity
THRESHOLD_HIGH = 0.275
THRESHOLD_MEDIUM = 0.230
THRESHOLD_LOW = 0.190
THRESHOLD_NO_MATCH = 0.180  # Below this, pure uncorrelated noise

@dataclass
class OptimizedAssignment:
    """Structured result for a single timeline scene."""
    beat_index: int
    image_filename: Optional[str]
    confidence: float
    confidence_level: str  # HIGH, MEDIUM, LOW, NO_MATCH
    is_manual_review_needed: bool
    is_user_override: bool
    evidence_reasons: List[str]
    top_candidates: List[Dict[str, Any]] = field(default_factory=list)
    rejection_trace: List[Dict[str, Any]] = field(default_factory=list)

class GlobalTimelineOptimizer:
    """
    Solves optimal sequence-wide image assignment for video timelines.
    Prevents greedy local suboptimal choices and ensures visual diversity.
    """

    def __init__(
        self,
        min_match_threshold: float = THRESHOLD_NO_MATCH,
        consecutive_duplicate_penalty: float = 0.25,
        temporal_window_decay: float = 0.12
    ):
        self.min_match_threshold = min_match_threshold
        self.consecutive_duplicate_penalty = consecutive_duplicate_penalty
        self.temporal_window_decay = temporal_window_decay

    @staticmethod
    def solve_linear_sum_assignment(cost_matrix: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """
        Solves minimum cost bipartite matching using standard linear sum assignment.
        Falls back to greedy auction algorithm if scipy is not installed.
        """
        try:
            from scipy.optimize import linear_sum_assignment
            return linear_sum_assignment(cost_matrix)
        except ImportError:
            # High-performance auction/greedy matching fallback
            n_rows, n_cols = cost_matrix.shape
            row_ind = np.arange(n_rows)
            col_ind = np.zeros(n_rows, dtype=int)
            available_cols = set(range(n_cols))
            
            # Sort rows by hardest-to-match first (highest minimal cost)
            row_order = np.argsort([cost_matrix[r].min() for r in range(n_rows)])
            
            for r in row_order:
                best_c = None
                best_cost = float("inf")
                for c in available_cols:
                    if cost_matrix[r, c] < best_cost:
                        best_cost = cost_matrix[r, c]
                        best_c = c
                if best_c is not None:
                    col_ind[r] = best_c
                    available_cols.remove(best_c)
                else:
                    # Fallback to absolute best col if all taken
                    col_ind[r] = int(np.argmin(cost_matrix[r]))
            return row_ind, col_ind

    def optimize_timeline(
        self,
        similarity_matrix: np.ndarray,      # Shape: (num_beats, num_images)
        image_filenames: List[str],
        user_overrides: Optional[Dict[int, str]] = None,
        locked_scenes: Optional[Set[int]] = None,
        sequence_continuity_lambda: float = 0.0,
        allow_consecutive_holds: Optional[List[bool]] = None
    ) -> List[OptimizedAssignment]:
        """
        Globally optimizes the complete timeline.
        Guarantees:
          - Preserves 100% of user_overrides / locked_scenes.
          - Incorporates calibrated sequence narrative progression when requested.
          - Penalizes unnecessary adjacent duplicate reuse while permitting intentional holds.
          - Identifies scenes with zero visual evidence as NO_MATCH.
        """
        num_beats, num_images = similarity_matrix.shape
        user_overrides = user_overrides or {}
        locked_scenes = locked_scenes or set()

        # Build Benefit Matrix from raw similarities
        benefit_matrix = similarity_matrix.copy()

        # Apply Narrative Sequence Continuity Prior if requested (§6.3, Storyboard Awareness)
        if sequence_continuity_lambda > 0.0 and num_beats > 1 and num_images > 1:
            for r in range(num_beats):
                p_b = r / float(max(1, num_beats - 1))
                for c in range(num_images):
                    p_img = c / float(max(1, num_images - 1))
                    delta = abs(p_b - p_img)
                    seq_prior = float(np.exp(- (delta ** 2) / (2.0 * (0.25 ** 2))))
                    benefit_matrix[r, c] += sequence_continuity_lambda * seq_prior

        # Apply hard user override constraints:
        # A locked image receives benefit +1000.0, non-selected images receive -1000.0
        for b_idx in range(num_beats):
            if b_idx in user_overrides:
                target_fn = user_overrides[b_idx]
                for img_idx, fn in enumerate(image_filenames):
                    if fn == target_fn:
                        benefit_matrix[b_idx, img_idx] = 1000.0
                    else:
                        benefit_matrix[b_idx, img_idx] = -1000.0

        # Handle case where num_beats > num_images (smart repetition expansion)
        if num_beats > num_images:
            repeats = math.ceil(num_beats / float(num_images))
            extended_cols = []
            for rep in range(repeats):
                # Repetition penalty increases with each repeated reuse layer
                decay = rep * self.temporal_window_decay
                extended_cols.append(benefit_matrix - decay)
            B_mat_ext = np.hstack(extended_cols)
        else:
            B_mat_ext = benefit_matrix

        cost_matrix = -B_mat_ext.copy()
        row_ind, col_ind = self.solve_linear_sum_assignment(cost_matrix)

        # Iterative Adjacent Duplicate Suppression & Conflict Resolution (§13, §18)
        # Penalizes placing identical image on consecutive beats unless marked as intentional hold
        resolved_duplicate_beats = set()
        for _ in range(3):
            has_unwanted_duplicate = False
            for r in range(1, num_beats):
                prev_c = int(col_ind[r - 1]) % num_images
                curr_c = int(col_ind[r]) % num_images
                if prev_c == curr_c:
                    is_intentional_hold = bool(
                        allow_consecutive_holds and
                        r < len(allow_consecutive_holds) and
                        allow_consecutive_holds[r]
                    )
                    is_override = (r in user_overrides)
                    if not is_intentional_hold and not is_override:
                        has_unwanted_duplicate = True
                        resolved_duplicate_beats.add(r)
                        cost_matrix[r, col_ind[r]] += self.consecutive_duplicate_penalty
            if has_unwanted_duplicate:
                row_ind, col_ind = self.solve_linear_sum_assignment(cost_matrix)
            else:
                break

        # Hard Inviolability Guarantee for Manual Scene Locks (§20, §29)
        for b_idx, target_fn in user_overrides.items():
            if 0 <= b_idx < num_beats and target_fn in image_filenames:
                col_target = image_filenames.index(target_fn)
                if (col_ind[b_idx] % num_images) != col_target:
                    # Find unconstrained row that was assigned col_target and swap
                    for other_r in range(num_beats):
                        if other_r != b_idx and (col_ind[other_r] % num_images) == col_target and other_r not in user_overrides:
                            col_ind[other_r] = col_ind[b_idx]
                            break
                    col_ind[b_idx] = col_target

        assignments: List[OptimizedAssignment] = []
        recent_assigned: List[str] = []

        for r in range(num_beats):
            is_override = (r in user_overrides)
            if is_override and user_overrides[r] in image_filenames:
                assigned_fn = user_overrides[r]
                c = image_filenames.index(assigned_fn)
            else:
                c = col_ind[r] % num_images
                assigned_fn = image_filenames[c]
            raw_sim = float(similarity_matrix[r, c])

            # Evaluate candidate ranking for this beat
            candidates_ranked = []
            for img_i, fn in enumerate(image_filenames):
                s = float(similarity_matrix[r, img_i])
                candidates_ranked.append({"image": fn, "similarity": round(s, 4)})
            candidates_ranked.sort(key=lambda x: x["similarity"], reverse=True)

            # Evaluate confidence and no-match status
            reasons = []
            if is_override:
                conf = 1.0
                conf_level = "HIGH"
                review_needed = False
                reasons.append("explicit_user_override")
            elif raw_sim < self.min_match_threshold:
                conf = round(raw_sim, 4)
                conf_level = "NO_MATCH"
                review_needed = True
                reasons.append("no_matching_image_in_library")
                reasons.append(f"similarity_{raw_sim:.3f}_below_threshold_{self.min_match_threshold}")
            elif raw_sim < THRESHOLD_LOW:
                conf = round(raw_sim, 4)
                conf_level = "LOW"
                review_needed = True
                reasons.append("low_visual_evidence")
            elif raw_sim < THRESHOLD_MEDIUM:
                conf = round(raw_sim, 4)
                conf_level = "MEDIUM"
                review_needed = False
                reasons.append("moderate_semantic_affinity")
            else:
                conf = round(raw_sim, 4)
                conf_level = "HIGH"
                review_needed = False
                reasons.append("strong_neural_semantic_match")

            # Narrative continuity prior note
            if sequence_continuity_lambda > 0.0:
                reasons.append("narrative_storyboard_continuity")

            # Check consecutive duplicate or intentional hold
            if recent_assigned and recent_assigned[-1] == assigned_fn and not is_override:
                is_intentional = bool(
                    allow_consecutive_holds and
                    r < len(allow_consecutive_holds) and
                    allow_consecutive_holds[r]
                )
                if is_intentional:
                    reasons.append("intentional_visual_hold")
                else:
                    reasons.append("consecutive_reuse")

            if r in resolved_duplicate_beats:
                reasons.append("adjacent_duplicate_resolved")

            # Build rejection trace
            rejection_trace = []
            for rej in candidates_ranked:
                if rej["image"] == assigned_fn:
                    continue
                diff = raw_sim - rej["similarity"]
                rejection_trace.append({
                    "image": rej["image"],
                    "similarity": rej["similarity"],
                    "delta_vs_winner": round(diff, 4)
                })
                if len(rejection_trace) >= 3:
                    break

            assignments.append(OptimizedAssignment(
                beat_index=r,
                image_filename=assigned_fn if conf_level != "NO_MATCH" else None,
                confidence=conf,
                confidence_level=conf_level,
                is_manual_review_needed=review_needed,
                is_user_override=is_override,
                evidence_reasons=reasons,
                top_candidates=candidates_ranked[:3],
                rejection_trace=rejection_trace
            ))
            recent_assigned.append(assigned_fn)

        return assignments
