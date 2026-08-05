# ReHairAnalytics (HairTrack AI) — PRD

## Original Problem Statement
Web app to objectively track hair growth over time using AI. NOT a medical diagnosis tool.
Users sign up, create a profile, start a tracking journey, upload standardized scalp photos
(front/left/right/top/back), receive AI image-quality feedback, get density/hairline/coverage
estimates, compare vs previous & baseline, view a timeline + progress charts, and read a
non-diagnostic LLM summary. Export data.

## Chosen Architecture (adapted from Next.js/Postgres/Clerk spec)
- Frontend: React 19 + TailwindCSS + shadcn/ui + React Query + Framer Motion + Recharts
- Backend: FastAPI (all routes under /api)
- Database: MongoDB (collections: users, user_sessions, profiles, tracking_sessions, images, analysis)
- Storage: Emergent object storage (S3-compatible)
- Auth: Emergent-managed Google OAuth (session_token httpOnly cookie, 7d)
- AI: OpenAI gpt-5.6-terra via Emergent Universal Key (emergentintegrations) for image quality,
  hair metric estimation (density/coverage/hairline/overall/confidence), and non-diagnostic summary.

## User Personas
- Individual tracking hair density/hairline over weeks/months for treatment monitoring.

## Core Requirements (static)
1. Google sign-in + profile. 2. Upload baseline photo set. 3. AI quality feedback (reject <60).
4. Objective density/coverage/hairline scores. 5. Weekly follow-up uploads. 6. Compare vs
previous & baseline. 7. Progress charts + LLM non-diagnostic summary. 8. Export data & images.

## Implemented (2026-08-05)
- Landing page (hero, features, how-it-works, pricing placeholder, Google login).
- Google OAuth flow (AuthCallback + ProtectedRoute + AuthProvider), onboarding/profile.
- Dashboard: streak, latest upload, est. progress, quality, density/coverage/hairline charts, milestones.
- New Upload: 5-view drag&drop + camera capture with silhouette alignment overlay, per-view AI quality gate.
- Results: density/coverage/hairline/overall score rings, quality/confidence/visible-scalp, vs previous & baseline deltas, AI insight, gallery.
- Timeline: milestone list + multi-metric chart, click opens comparison.
- Settings: dark mode, units, export JSON, download images, delete account, privacy.
- Backend APIs: auth, profile, sessions, upload, analyze, timeline, progress, files, export, account.
- Lazy session creation on first upload; softened AI quality prompt to reduce false rejections.
- Verified: 20/20 backend pytest + frontend auth-gated flows (testing iteration_1, 100%).

## Backlog / Remaining (P1/P2)
- P1: Weekly email/push reminders (notifications) — not yet implemented.
- P2: Real CV (OpenCV/MediaPipe) hairline polygon + strand counting (spec future features).
- P2: Growth prediction, treatment-effectiveness scoring, clinic/dermatologist dashboards.
- P2: Raise 502 on AI failure instead of neutral fallback scores (currently graceful fallback).

## Next Tasks
- Add weekly reminder notifications.
- Optional side-by-side baseline-vs-current image comparison view on Results.
