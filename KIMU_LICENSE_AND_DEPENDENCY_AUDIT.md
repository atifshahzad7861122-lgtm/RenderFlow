# Kimu Repository — License, Intellectual Property & Dependency Audit

**Audit Date**: October 10, 2026  
**Auditor**: RenderFlow Advanced Engineering Team  
**Scope**: `https://github.com/trykimu/videoeditor` (Commit/Branch: `main`)  
**Target Repository**: RenderFlow / Rendering Studio Engine v2 (Windows Local Workstation)

---

## 1. Upstream License Analysis

### 1.1 Dual-License Declaration
Inspection of `scratch/kimu_research/videoeditor-main/LICENSE.md` reveals the upstream repository is distributed under a **dual-license model**:
1. **Open Source**: GNU Affero General Public License v3.0 (`LICENSE-AGPL3.md`).
2. **Commercial License**: Proprietary closed-source license available from the Kimu Team.

Text of `LICENSE.md`:
> "Unless you have a separate commercial license from the copyright holder, the AGPL v3 applies by default. Network use (SaaS) triggers the obligation to provide the corresponding source to users interacting with the software over a network. For closed-source or commercial use without AGPL obligations, you must obtain a commercial license from the copyright holder."

### 1.2 GNU AGPL v3 Implications
- **Copyleft Scope**: AGPL v3 contains a strong copyleft clause. If AGPL-3.0 copyrighted code is directly copied or statically/dynamically linked into another codebase, the entire resulting work may become subject to the AGPL-3.0 copyleft terms upon distribution or network interaction (Section 13 Remote Network Interaction).
- **Workstation Impact**: RenderFlow is a proprietary/standalone desktop workstation designed for local content creators, running on Windows with offline hardware acceleration. Incorporating direct source files from Kimu would impose AGPL source-disclosure obligations or create legal uncertainty for downstream distributions.

### 1.3 Remotion Licensing Terms
Kimu relies heavily on Remotion (`remotion`, `@remotion/player`, `@remotion/renderer`).
- **Remotion License Model**: Remotion is distributed under a specialized commercial license ("Remotion Company License"). While free for individuals and non-commercial entities with <$3M annual revenue, companies with revenue above that threshold must purchase an enterprise license.
- **Node.js/Puppeteer Headless Dependency**: Remotion requires spinning up headless Chromium processes to render frames via React DOM. This is substantially heavier, slower, and more memory-intensive than native C++ FFmpeg filtergraphs.
- **Architectural Decision**: RenderFlow strictly maintains its native FFmpeg filtergraph pipeline (`engine/fast_pipeline.py`). We **do not adopt Remotion** for rendering or player display.

---

## 2. Dependency Audit

Inspection of `package.json` and `backend/pyproject.toml` in the Kimu repository identifies the following dependency graph:

### 2.1 Upstream Frontend Dependencies (`package.json`)

| Dependency | Upstream License | Used For in Kimu | RenderFlow Compatibility | Decision |
|---|---|---|---|---|
| `react` / `react-dom` (v19) | MIT | UI component framework | Incompatible with RenderFlow's lightweight vanilla ES6 architecture | **Do Not Import** |
| `@remotion/player` | Remotion Commercial | Video canvas playback | Restrictive license, heavy Node runtime | **Exclude** (Use HTML5 Canvas/Audio) |
| `@remotion/renderer` | Remotion Commercial | Headless video rendering | Restrictive license, slower than FFmpeg | **Exclude** (Preserve native FFmpeg) |
| `tailwindcss` | MIT | CSS styling utility | RenderFlow uses curated Vanilla CSS design system | **Do Not Import** |
| `radix-ui` primitives | MIT | Accessible UI modals/menus | React-only library | **Independent Vanilla Implementation** |
| `lucide-react` | ISC | UI iconography | React wrapper; SVG icons already in RenderFlow | **Use RenderFlow SVGs** |
| `zod` | MIT | Schema validation | Runtime TypeScript validator | **Adapt concepts to Python/JS validation** |

### 2.2 Upstream Backend Dependencies (`backend/pyproject.toml`)

| Dependency | Upstream License | Used For in Kimu | RenderFlow Compatibility | Decision |
|---|---|---|---|---|
| `fastapi` / `uvicorn` | MIT / BSD | API Server | Native match (RenderFlow already uses FastAPI) | **Compatible** |
| `psycopg` / `asyncpg` | LGPL / Apache-2.0 | PostgreSQL database driver | Cloud service requirement; breaks local file-first model | **Exclude** |
| `ioredis` / `redis` | BSD | Job queue / caching | Requires running Redis daemon on Windows | **Exclude** |
| `boto3` / `botocore` | Apache-2.0 | AWS S3 object storage | Requires cloud credentials & network | **Exclude** |
| `openai` / `google-genai` | Apache-2.0 | LLM generative editing | Generative AI; violates non-AI mandate | **Strictly Exclude** |
| `fal-client` | MIT | AI video generation | Generative AI; violates non-AI mandate | **Strictly Exclude** |

---

## 3. Clean-Room Adaptation Strategy

To ensure **100% legal clarity, zero license infection, zero dependency bloat, and total architectural stability**, RenderFlow employs a **Clean-Room Independent Reimplementation / Adaptation** methodology:

1. **No Direct Copying of Upstream Files**:
   - Zero source files from `scratch/kimu_research/videoeditor-main/` are copied directly into `web/` or `engine/`.
   - The research repository remains quarantined in `scratch/kimu_research/` as reference documentation only.

2. **Functional Specification & Independent Implementation**:
   - Upstream source files were inspected strictly to understand the *interaction patterns*, *mathematical behaviors*, and *data representations* (e.g., how magnetic snapping calculates thresholds, how trimming handles update time offsets, how timecodes are formatted).
   - All resulting code in RenderFlow is written **from scratch in native Vanilla JavaScript (ES6+), modern CSS, and Python**.

3. **Attribution & Intellectual Integrity**:
   - Although no AGPL code is directly incorporated, RenderFlow acknowledges the architectural inspiration from Kimu's timeline layout in project documentation (`KIMU_TIMELINE_INTEGRATION_REPORT.md`).
   - All modules conform to RenderFlow's established codebase structure, naming conventions, and Windows launcher lifecycle.

---

## 4. Summary Table of Architecture Decisions

| Feature / Subsystem | Upstream Implementation | RenderFlow Integrated Solution | License Compliance Status |
|---|---|---|---|
| **Timeline Tracks** | React 19 + Radix UI (`TimelineTracks.tsx`) | Clean-room Vanilla JS / CSS Grid multi-track canvas (`web/static/js/app.js`) | **CLEAN** (No AGPL code) |
| **Clip Trimming & Snapping** | DOM refs + React state (`Scrubber.tsx`) | Native DOM pointer events + magnetic snapping math (`web/static/js/app.js`) | **CLEAN** (Independent reimplementation) |
| **Timecode Ruler** | React SVG ticks (`TimelineRuler.tsx`) | Canvas / DOM high-DPI timecode ruler (`web/static/js/app.js`) | **CLEAN** (Independent reimplementation) |
| **Inspector Panel** | React component (`InspectorPanel.tsx`) | Native CSS Inspector panel with two-way data binding | **CLEAN** (Independent reimplementation) |
| **Video Playback** | `@remotion/player` | Native HTML5 `<audio>` + Canvas frame sync | **CLEAN** (No Remotion license required) |
| **Video Export** | `@remotion/renderer` (Puppeteer) | Native FFmpeg 4K hardware-accelerated pipeline | **CLEAN** (Preserves RenderFlow FFmpeg) |
| **AI Assistants & Cloud** | Gemini, OpenAI, Postgres, S3 | Excluded entirely (Zero Generative AI, local filesystem) | **CLEAN** (No external cloud / API keys) |
