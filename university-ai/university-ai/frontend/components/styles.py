"""
frontend/components/styles.py
═════════════════════════════
CSS premium partajat între toate paginile.

Folosim Streamlit `st.markdown(..., unsafe_allow_html=True)` pentru injecție.
Definim variabile CSS (--primary, --bg-card etc.) ca să fie ușor de re-tematizat.
"""

import streamlit as st


# ── Paleta + variabile globale ────────────────────────────────────────────────

GLOBAL_CSS = """
<style>
:root {
    --primary: #4361ee;
    --primary-light: #6388ff;
    --primary-dark: #3a0ca3;
    --accent: #7209b7;
    --success: #4cc9a7;
    --warning: #f59e0b;
    --danger: #ef476f;

    --bg-deep: #0a0e1a;
    --bg-card: #1a1f2e;
    --bg-card-hover: #232938;
    --bg-elevated: #252b3d;
    --border: #2d3548;
    --border-strong: #3d4660;

    --text-primary: #ffffff;
    --text-secondary: #b8c2d1;
    --text-muted: #7d8696;

    --gradient-hero: linear-gradient(135deg, #4361ee 0%, #7209b7 50%, #f72585 100%);
    --gradient-card: linear-gradient(135deg, rgba(67,97,238,0.08), rgba(114,9,183,0.05));
}

/* ═══ RESET & BASE ═══ */
.main .block-container {
    padding-top: 2rem;
    max-width: 1280px;
}

[data-testid="stHeader"] {
    background: transparent;
}

/* ═══ TIPOGRAFIE ═══ */
h1, h2, h3, h4 {
    letter-spacing: -0.02em;
}

/* ═══ BUTOANE ═══ */
.stButton > button {
    border-radius: 10px;
    font-weight: 600;
    transition: all 0.2s ease;
    border: 1px solid var(--border-strong);
}

.stButton > button[kind="primary"] {
    background: linear-gradient(135deg, var(--primary), var(--primary-dark));
    border: none;
    color: white;
    box-shadow: 0 4px 14px rgba(67, 97, 238, 0.3);
}
.stButton > button[kind="primary"]:hover {
    transform: translateY(-2px);
    box-shadow: 0 8px 24px rgba(67, 97, 238, 0.45);
}

/* ═══ INPUTS ═══ */
.stTextInput input,
.stTextArea textarea,
section[data-testid="stChatInput"] textarea {
    border-radius: 10px !important;
    border: 1px solid var(--border) !important;
    transition: border-color 0.15s, box-shadow 0.15s !important;
}
.stTextInput input:focus,
.stTextArea textarea:focus,
section[data-testid="stChatInput"] textarea:focus {
    border-color: var(--primary) !important;
    box-shadow: 0 0 0 3px rgba(67, 97, 238, 0.15) !important;
}

/* ═══ BADGE-URI & CHIPS ═══ */
.source-badge {
    background: linear-gradient(135deg, #1a3a2a, #0f2a1f);
    color: #7ddc9d;
    border: 1px solid #2d6a4f;
    padding: 4px 12px;
    border-radius: 16px;
    font-size: 0.80em;
    margin: 3px 4px 3px 0;
    display: inline-block;
    font-family: 'SF Mono', Consolas, monospace;
}
.score-chip {
    background: linear-gradient(135deg, #1a2a3a, #0f1f2a);
    color: #7db8dc;
    border: 1px solid #2d4f6a;
    padding: 2px 8px;
    border-radius: 10px;
    font-size: 0.72em;
    margin-left: 6px;
}
.rerank-chip {
    background: linear-gradient(135deg, #2a1a3a, #1f0f2a);
    color: #c89ddc;
    border: 1px solid #6a2d4f;
    padding: 2px 8px;
    border-radius: 10px;
    font-size: 0.72em;
}
.ocr-chip {
    background: linear-gradient(135deg, #3a2a1a, #2a1f0f);
    color: #dcb87d;
    border: 1px solid #6a4f2d;
    padding: 2px 8px;
    border-radius: 10px;
    font-size: 0.70em;
    font-weight: 600;
}

/* ═══ STATUS PILLS ═══ */
.status-pill {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 5px 14px;
    border-radius: 20px;
    background: rgba(255,255,255,0.04);
    border: 1px solid var(--border);
    font-size: 0.85em;
}
.status-dot {
    width: 8px; height: 8px;
    border-radius: 50%;
    animation: pulse 2s infinite;
}
.status-dot.ok  { background: #4cc9a7; box-shadow: 0 0 8px #4cc9a7; }
.status-dot.err { background: #ef476f; }
.status-dot.warn { background: #f59e0b; }

@keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.5; }
}

/* ═══ CITATION BLOCK ═══ */
.citation-block {
    background: rgba(255, 217, 61, 0.05);
    border-left: 3px solid #ffd93d;
    padding: 10px 14px;
    margin: 8px 0;
    border-radius: 0 8px 8px 0;
    font-size: 0.88em;
}

/* ═══ THINKING ANIMATION ═══ */
.thinking {
    display: inline-block;
    color: var(--text-muted);
    font-style: italic;
}
.thinking::after {
    content: '';
    animation: dots 1.5s steps(4, end) infinite;
}
@keyframes dots {
    0%, 20% { content: ''; }
    40% { content: '.'; }
    60% { content: '..'; }
    80%, 100% { content: '...'; }
}

/* ═══ HOME PAGE — HERO ═══ */
.hero-container {
    text-align: center;
    padding: 80px 20px 60px;
    background:
        radial-gradient(ellipse at top, rgba(67, 97, 238, 0.15), transparent 70%),
        radial-gradient(ellipse at bottom right, rgba(247, 37, 133, 0.08), transparent 60%);
    border-radius: 24px;
    margin-bottom: 40px;
    position: relative;
    overflow: hidden;
}
.hero-badge {
    display: inline-block;
    padding: 6px 16px;
    background: rgba(67, 97, 238, 0.12);
    border: 1px solid rgba(67, 97, 238, 0.3);
    border-radius: 20px;
    color: #a3b5ff;
    font-size: 0.85em;
    font-weight: 600;
    margin-bottom: 24px;
    letter-spacing: 0.5px;
}
.hero-title {
    font-size: 4em;
    font-weight: 800;
    line-height: 1.1;
    margin: 0 0 24px 0;
    background: var(--gradient-hero);
    background-clip: text;
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    letter-spacing: -0.03em;
}
.hero-subtitle {
    font-size: 1.3em;
    color: var(--text-secondary);
    max-width: 720px;
    margin: 0 auto 32px;
    line-height: 1.6;
}
@media (max-width: 768px) {
    .hero-title { font-size: 2.5em; }
    .hero-subtitle { font-size: 1em; }
}

/* ═══ HOME PAGE — FEATURE CARDS ═══ */
.feature-card {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 16px;
    padding: 28px 24px;
    height: 100%;
    transition: all 0.25s ease;
    position: relative;
    overflow: hidden;
}
.feature-card::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 3px;
    background: var(--gradient-hero);
    opacity: 0;
    transition: opacity 0.25s;
}
.feature-card:hover {
    transform: translateY(-4px);
    border-color: var(--primary);
    background: var(--bg-card-hover);
    box-shadow: 0 20px 40px rgba(0, 0, 0, 0.3);
}
.feature-card:hover::before {
    opacity: 1;
}
.feature-icon {
    font-size: 2.5em;
    margin-bottom: 16px;
    display: inline-block;
}
.feature-title {
    font-size: 1.2em;
    font-weight: 700;
    color: var(--text-primary);
    margin-bottom: 12px;
}
.feature-desc {
    color: var(--text-secondary);
    line-height: 1.6;
    font-size: 0.95em;
}

/* ═══ STATS SECTION ═══ */
.stat-card {
    text-align: center;
    padding: 24px;
    background: var(--gradient-card);
    border: 1px solid var(--border);
    border-radius: 16px;
}
.stat-value {
    font-size: 2.5em;
    font-weight: 800;
    background: var(--gradient-hero);
    background-clip: text;
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    line-height: 1;
}
.stat-label {
    margin-top: 8px;
    color: var(--text-muted);
    font-size: 0.85em;
    text-transform: uppercase;
    letter-spacing: 1px;
    font-weight: 600;
}

/* ═══ AUTH FORMS ═══ */
.auth-container {
    max-width: 460px;
    margin: 40px auto;
    padding: 40px;
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 20px;
    box-shadow: 0 24px 48px rgba(0, 0, 0, 0.3);
}
.auth-title {
    font-size: 2em;
    font-weight: 800;
    background: var(--gradient-hero);
    background-clip: text;
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    margin-bottom: 8px;
    text-align: center;
}
.auth-subtitle {
    text-align: center;
    color: var(--text-muted);
    margin-bottom: 32px;
}

/* ═══ USER CHIP ═══ */
.user-chip {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 10px 14px;
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 12px;
    margin-bottom: 12px;
}
.user-avatar {
    width: 36px; height: 36px;
    border-radius: 50%;
    background: var(--gradient-hero);
    display: flex;
    align-items: center;
    justify-content: center;
    color: white;
    font-weight: 700;
    font-size: 0.95em;
}
.user-name {
    font-weight: 600;
    color: var(--text-primary);
    line-height: 1.2;
}
.user-meta {
    font-size: 0.78em;
    color: var(--text-muted);
}

/* ═══ CHAT HISTORY SIDEBAR ═══ */
.chat-history-item {
    display: block;
    padding: 10px 12px;
    border-radius: 8px;
    background: transparent;
    border: 1px solid transparent;
    margin-bottom: 4px;
    cursor: pointer;
    transition: all 0.15s;
}
.chat-history-item:hover {
    background: var(--bg-card-hover);
    border-color: var(--border);
}
.chat-history-item.active {
    background: rgba(67, 97, 238, 0.12);
    border-color: var(--primary);
}
.chat-title-text {
    font-weight: 500;
    color: var(--text-primary);
    font-size: 0.9em;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}
.chat-date-text {
    font-size: 0.72em;
    color: var(--text-muted);
    margin-top: 2px;
}

/* ═══ GUEST WARNING ═══ */
.guest-warning {
    background: linear-gradient(135deg, rgba(245, 158, 11, 0.1), rgba(239, 71, 111, 0.08));
    border: 1px solid rgba(245, 158, 11, 0.4);
    border-radius: 12px;
    padding: 14px 18px;
    margin: 12px 0;
    color: #ffc56b;
}

/* ═══ INTRO BOX (chat) ═══ */
.intro-box {
    background: var(--gradient-card);
    border: 1px solid rgba(67, 97, 238, 0.3);
    border-radius: 16px;
    padding: 24px 28px;
    margin-bottom: 16px;
}
.intro-box h4 {
    margin-top: 0;
    color: #a3b5ff;
}
.intro-box code {
    background: rgba(0,0,0,0.3);
    padding: 2px 8px;
    border-radius: 4px;
    color: #ffd93d;
}

/* ═══ FOOTER ═══ */
.app-footer {
    text-align: center;
    padding: 32px 16px 16px;
    color: var(--text-muted);
    font-size: 0.85em;
    border-top: 1px solid var(--border);
    margin-top: 48px;
}

/* ═══ HIDE STREAMLIT BRANDING ═══ */
#MainMenu { visibility: hidden; }
footer { visibility: hidden; }
header[data-testid="stHeader"] { background: transparent; }
</style>
"""


def inject_global_css() -> None:
    """Apelată la începutul fiecărei pagini pentru a aplica stilurile."""
    st.markdown(GLOBAL_CSS, unsafe_allow_html=True)
