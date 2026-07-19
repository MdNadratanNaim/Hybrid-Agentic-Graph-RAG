"""
styles.py
---------
Design tokens + CSS injection.

Direction: an instrumentation console for a multi-stage pipeline, not a
generic chat UI. Graphite base (not pure black) / warm off-white paper
base for light mode, a muted brass/amber accent used consistently as both
the brand color and the "active" signal color, Space Grotesk for display
type, IBM Plex Sans for body copy, JetBrains Mono for stage codes /
latencies / logs.

IMPORTANT — why this file does more than style custom `st.markdown` divs:
Streamlit's native widgets (text areas, buttons, expanders, tabs, radio,
sliders, chat bubbles, dataframes...) are themed by Streamlit's OWN engine,
not by CSS variables scoped to our custom elements. If we only styled our
own `.signal-rail` / `.source-card` divs, native widgets would keep
whatever theme the browser/server defaults to -- which is how you get
"light mode" pages with dark-on-dark native inputs. So below we (a)
override Streamlit's own theme CSS variables, and (b) add explicit
`data-testid`-scoped rules (more stable across Streamlit versions than the
hashed `st-emotion-cache-*` classnames) for the handful of widgets that
don't fully inherit from those variables.
"""

import streamlit as st

FONT_IMPORT = (
    "@import url('https://fonts.googleapis.com/css2?"
    "family=Space+Grotesk:wght@500;600;700&"
    "family=IBM+Plex+Sans:wght@400;500;600&"
    "family=JetBrains+Mono:wght@400;500;600&display=swap');"
)

DARK = {
    "bg": "#181B20",
    "bg_alt": "#1F232A",
    "panel": "#22262E",
    "panel_2": "#282D36",
    "panel_border": "#383E47",
    "text": "#ECE9E3",
    "text_muted": "#9CA3AD",
    "accent": "#C98A3B",
    "accent_rgb": "201, 138, 59",
    "accent_text": "#16181C",
    "accent_soft": "#3A2E1C",
    "success": "#6FAE7A",
    "success_soft": "#26332A",
    "fail": "#D07A63",
    "fail_soft": "#3A2721",
    "info": "#8FA8C4",
    "skip": "#4A4F58",
    "input_bg": "#1D2027",
    "shadow": "0 1px 2px rgba(0,0,0,0.35)",
}

LIGHT = {
    "bg": "#FBFAF7",
    "bg_alt": "#F1EEE6",
    "panel": "#FFFFFF",
    "panel_2": "#F6F4EE",
    "panel_border": "#E1DCCE",
    "text": "#211E19",
    "text_muted": "#5B5750",
    "accent": "#A8681F",
    "accent_rgb": "168, 104, 31",
    "accent_text": "#FFFFFF",
    "accent_soft": "#F1E1C4",
    "success": "#2F7A45",
    "success_soft": "#E3EFE4",
    "fail": "#A23F27",
    "fail_soft": "#F5E3DD",
    "info": "#3C5E82",
    "skip": "#CFC9B8",
    "input_bg": "#FFFFFF",
    "shadow": "0 1px 3px rgba(40,35,20,0.08)",
}


def get_tokens(theme: str) -> dict:
    return DARK if theme == "dark" else LIGHT


def inject_css(theme: str = "dark") -> None:
    c = get_tokens(theme)

    css = f"""
    <style>
    {FONT_IMPORT}

    :root, .stApp {{
        --bg: {c['bg']};
        --bg-alt: {c['bg_alt']};
        --panel: {c['panel']};
        --panel-2: {c['panel_2']};
        --panel-border: {c['panel_border']};
        --text: {c['text']};
        --text-muted: {c['text_muted']};
        --accent: {c['accent']};
        --accent-rgb: {c['accent_rgb']};
        --accent-text: {c['accent_text']};
        --accent-soft: {c['accent_soft']};
        --success: {c['success']};
        --success-soft: {c['success_soft']};
        --fail: {c['fail']};
        --fail-soft: {c['fail_soft']};
        --info: {c['info']};
        --skip: {c['skip']};
        --input-bg: {c['input_bg']};
        --shadow: {c['shadow']};

        --primary-color: {c['accent']};
        --background-color: {c['bg']};
        --secondary-background-color: {c['panel']};
        --text-color: {c['text']};
    }}

    html, body, [class*="css"] {{
        font-family: 'IBM Plex Sans', sans-serif;
    }}

    .stApp, [data-testid="stAppViewContainer"], [data-testid="stAppViewBlockContainer"],
    .main, section.main {{
        background: var(--bg) !important;
        color: var(--text) !important;
    }}

    section[data-testid="stSidebar"] {{
        background: var(--bg-alt) !important;
        border-right: 1px solid var(--panel-border);
    }}
    section[data-testid="stSidebar"] * {{
        color: var(--text) !important;
    }}
    section[data-testid="stSidebar"] [data-testid="stCaptionContainer"] {{
        color: var(--text-muted) !important;
    }}

    /* The header bar (hamburger menu, "Deploy" button, running-man status)
       and the floating control used to re-open a collapsed sidebar. These
       had a background but no text/icon color, so their icons kept
       Streamlit's own internal theme color -- invisible against our
       overridden background. */
    [data-testid="stHeader"], [data-testid="stToolbar"],
    [data-testid="collapsedControl"], [data-testid="stSidebarCollapseButton"],
    [data-testid="stSidebarCollapsedControl"] {{
        color: var(--text) !important;
        background: var(--bg) !important;
    }}
    [data-testid="collapsedControl"] button, [data-testid="stSidebarCollapseButton"] button {{
        background: transparent !important;
        color: var(--text) !important;
    }}

    /* Systemic fix for the whole "icon disappears" class of bug: Streamlit's
       Material icons set their own fill as a presentation attribute or
       inline style tied to Streamlit's internal theme, independent of our
       tokens. Force every icon to take its color from its containing
       element instead, and make sure every place that gets a background in
       this file also gets an explicit foreground so the two can never end
       up matching by accident. */
    .stApp svg, .stApp svg path {{
        fill: currentColor !important;
    }}

    h1, h2, h3, h4, h5, .console-title {{
        font-family: 'Space Grotesk', sans-serif;
        letter-spacing: -0.01em;
        color: var(--text);
    }}
    p, span, label, div {{
        color: inherit;
    }}

    code, .mono, .stage-code, .latency, .stage-log-line {{
        font-family: 'JetBrains Mono', monospace !important;
    }}

    [data-testid="stTextArea"] textarea,
    [data-testid="stTextInput"] input,
    [data-testid="stNumberInput"] input {{
        background: var(--input-bg) !important;
        color: var(--text) !important;
        border: 1px solid var(--panel-border) !important;
        border-radius: 8px !important;
    }}
    [data-testid="stTextArea"] textarea::placeholder,
    [data-testid="stTextInput"] input::placeholder {{
        color: var(--text-muted) !important;
        opacity: 0.85;
    }}

    [data-testid="stFileUploaderDropzone"] {{
        background: var(--panel-2) !important;
        border: 1px dashed var(--panel-border) !important;
        color: var(--text) !important;
    }}
    [data-testid="stFileUploaderDropzone"] * {{ color: var(--text) !important; }}
    [data-testid="stFileUploaderDropzone"] small {{ color: var(--text-muted) !important; }}

    [data-baseweb="select"] > div, [data-baseweb="popover"] {{
        background: var(--input-bg) !important;
        color: var(--text) !important;
        border-color: var(--panel-border) !important;
    }}
    [data-baseweb="menu"] {{
        background: var(--panel) !important;
    }}
    [data-baseweb="menu"] li {{ color: var(--text) !important; }}
    [data-baseweb="menu"] li:hover {{ background: var(--panel-2) !important; }}

    [data-testid="stRadio"] label p, [data-testid="stCheckbox"] label p {{
        color: var(--text) !important;
    }}

    [data-testid="stSlider"] [data-testid="stTickBarMin"],
    [data-testid="stSlider"] [data-testid="stTickBarMax"] {{
        color: var(--text-muted) !important;
    }}
    [data-testid="stSlider"] div[role="slider"] {{
        background-color: var(--accent) !important;
    }}
    [data-testid="stSliderTickBar"], [data-testid="stTickBar"] {{
        background: var(--panel-border) !important;
    }}

    [data-testid="stExpander"] {{
        background: var(--panel) !important;
        border: 1px solid var(--panel-border) !important;
        border-radius: 10px !important;
    }}
    [data-testid="stExpander"] summary {{
        color: var(--text) !important;
    }}
    [data-testid="stExpander"] summary:hover {{
        color: var(--accent) !important;
    }}

    [data-testid="stForm"] {{
        background: var(--panel) !important;
        border: 1px solid var(--panel-border) !important;
        border-radius: 12px !important;
        padding: 1rem 1.1rem 0.6rem 1.1rem !important;
    }}

    [data-testid="stTabs"] [data-baseweb="tab-list"] {{
        background: transparent !important;
        border-bottom: 1px solid var(--panel-border) !important;
        gap: 0.25rem;
    }}
    [data-testid="stTabs"] [data-baseweb="tab"] {{
        color: var(--text-muted) !important;
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.82rem;
    }}
    [data-testid="stTabs"] [aria-selected="true"] {{
        color: var(--accent) !important;
    }}
    [data-testid="stTabs"] [data-baseweb="tab-highlight"] {{
        background-color: var(--accent) !important;
    }}

    [data-testid="stMetric"] {{
        background: var(--panel) !important;
        border: 1px solid var(--panel-border) !important;
        border-radius: 10px !important;
        padding: 0.6rem 0.8rem !important;
    }}
    [data-testid="stMetricLabel"] {{ color: var(--text-muted) !important; }}
    [data-testid="stMetricValue"] {{ color: var(--text) !important; font-family: 'JetBrains Mono', monospace; }}

    [data-testid="stDataFrame"] {{
        background: var(--panel) !important;
        border: 1px solid var(--panel-border) !important;
        border-radius: 8px;
    }}

    [data-testid="stChatMessage"] {{
        background: var(--panel) !important;
        color: var(--text) !important;
        border: 1px solid var(--panel-border) !important;
        border-radius: 12px !important;
        box-shadow: var(--shadow);
    }}
    [data-testid="stChatInput"] textarea {{
        background: var(--input-bg) !important;
        color: var(--text) !important;
    }}

    /* Captions can appear anywhere, not just in the sidebar. Previously only
       the sidebar rule set this, so captions in the main body kept
       Streamlit's own default muted color, which does not track our tokens. */
    [data-testid="stCaptionContainer"] {{
        color: var(--text-muted) !important;
    }}

    /* st.info / st.success / st.warning / st.error. These were entirely
       unstyled before, so they kept rendering with Streamlit's own base
       theme's alert colors -- the single biggest source of "dark box on a
       light page" in light mode. Base rule first (works across Streamlit
       versions even if the kind-specific testids below don't match),
       then kind-specific accents layered on top. */
    [data-testid="stAlert"] {{
        background: var(--panel) !important;
        border: 1px solid var(--panel-border) !important;
        border-radius: 8px !important;
        color: var(--text) !important;
    }}
    [data-testid="stAlert"] p, [data-testid="stAlert"] span, [data-testid="stAlert"] li {{
        color: var(--text) !important;
    }}
    [data-testid="stAlertContentInfo"] {{
        background: var(--bg-alt) !important; border-left: 3px solid var(--info) !important;
    }}
    [data-testid="stAlertContentSuccess"] {{
        background: var(--success-soft) !important; border-left: 3px solid var(--success) !important;
    }}
    [data-testid="stAlertContentWarning"] {{
        background: var(--accent-soft) !important; border-left: 3px solid var(--accent) !important;
    }}
    [data-testid="stAlertContentError"] {{
        background: var(--fail-soft) !important; border-left: 3px solid var(--fail) !important;
    }}

    /* st.toast */
    [data-testid="stToast"] {{
        background: var(--panel) !important;
        color: var(--text) !important;
        border: 1px solid var(--panel-border) !important;
    }}

    /* st.status(), a close cousin of stExpander */
    [data-testid="stStatusWidget"] {{
        background: var(--panel) !important;
        border: 1px solid var(--panel-border) !important;
        border-radius: 10px !important;
        color: var(--text) !important;
    }}

    /* Links in markdown / body text -- otherwise fall back to browser blue,
       which clashes with the amber accent in both themes. */
    .stApp a {{ color: var(--accent) !important; }}
    .stApp a:hover {{ filter: brightness(1.1); text-decoration: underline; }}

    /* st.code and inline `code` in markdown. We intentionally leave the
       syntax-highlighter's own token colors alone (that's a separate JS
       theme and fighting it token-by-token is brittle) but bring the
       surrounding chrome in line with the panel system so it doesn't look
       like a foreign element dropped onto the page. */
    [data-testid="stCodeBlock"] {{
        border: 1px solid var(--panel-border) !important;
        border-radius: 8px !important;
    }}
    [data-testid="stMarkdownContainer"] code, .stApp code:not(pre code) {{
        background: var(--panel-2) !important;
        color: var(--accent) !important;
        border: 1px solid var(--panel-border) !important;
        border-radius: 4px !important;
        padding: 0.1rem 0.35rem !important;
    }}

    /* st.toggle */
    [data-testid="stToggle"] label div[data-baseweb="checkbox"] div {{
        background: var(--skip) !important;
    }}
    [data-testid="stToggle"] label div[data-baseweb="checkbox"] div[aria-checked="true"] {{
        background: var(--accent) !important;
    }}

    /* st.multiselect tags/pills */
    [data-baseweb="tag"] {{
        background: var(--accent-soft) !important;
        border: 1px solid var(--accent) !important;
    }}
    [data-baseweb="tag"] span {{ color: var(--text) !important; }}
    [data-baseweb="tag"] svg {{ fill: var(--text-muted) !important; }}

    /* st.progress */
    [data-testid="stProgress"] > div > div > div {{
        background: var(--panel-border) !important;
    }}
    [data-testid="stProgress"] > div > div > div > div {{
        background: var(--accent) !important;
    }}

    /* Fill track behind the slider handle, in addition to the handle
       itself which was already covered above. */
    [data-testid="stSlider"] [data-baseweb="slider"] > div:nth-child(2) {{
        background: var(--panel-border) !important;
    }}
    [data-testid="stSlider"] [data-baseweb="slider"] > div:nth-child(2) > div {{
        background: var(--accent) !important;
    }}

    /* Download / link buttons ride a different class than st.button, so
       the earlier .stButton rule never reached them. */
    .stDownloadButton > button, .stLinkButton > a {{
        background: var(--accent) !important;
        color: var(--accent-text) !important;
        border: none !important;
        font-weight: 600;
        border-radius: 8px !important;
    }}
    .stDownloadButton > button:hover, .stLinkButton > a:hover {{
        filter: brightness(1.08);
        color: var(--accent-text) !important;
    }}

    /* Visible keyboard focus in both themes, since the browser default
       focus ring is low-contrast against custom panel colors. */
    button:focus-visible, a:focus-visible, input:focus-visible,
    textarea:focus-visible, [role="slider"]:focus-visible,
    [data-baseweb="select"]:focus-within {{
        outline: 2px solid var(--accent) !important;
        outline-offset: 2px !important;
    }}

    hr {{ border-color: var(--panel-border) !important; }}

    .console-header {{
        display: flex;
        align-items: baseline;
        justify-content: space-between;
        border-bottom: 1px solid var(--panel-border);
        padding-bottom: 0.6rem;
        margin-bottom: 1.1rem;
    }}
    .console-title {{
        font-size: 1.5rem;
        font-weight: 700;
        color: var(--text);
        margin: 0;
    }}
    .console-title .accent-dot {{ color: var(--accent); }}
    .console-subtitle {{ color: var(--text-muted); font-size: 0.85rem; margin-top: 0.15rem; }}
    .console-eyebrow {{
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.7rem;
        letter-spacing: 0.12em;
        text-transform: uppercase;
        color: var(--accent);
    }}

    .panel {{
        background: var(--panel);
        border: 1px solid var(--panel-border);
        border-radius: 10px;
        padding: 1rem 1.1rem;
        margin-bottom: 0.9rem;
    }}
    .source-card {{
        background: var(--panel);
        border: 1px solid var(--panel-border);
        border-left: 3px solid var(--accent);
        border-radius: 6px;
        padding: 0.7rem 0.9rem;
        margin-bottom: 0.6rem;
    }}
    .source-card .source-title {{ font-weight: 600; font-size: 0.92rem; color: var(--text); }}
    .source-card .source-meta {{
        color: var(--text-muted);
        font-size: 0.78rem;
        font-family: 'JetBrains Mono', monospace;
        margin-top: 0.15rem;
    }}
    .source-card .source-body {{ color: var(--text); }}

    .signal-rail {{
        display: flex;
        align-items: flex-start;
        overflow-x: auto;
        gap: 0;
        padding: 1rem 0.4rem 0.5rem 0.4rem;
        background: var(--bg-alt);
        border: 1px solid var(--panel-border);
        border-radius: 10px;
    }}
    .signal-node-wrap {{ display: flex; align-items: center; flex: 0 0 auto; }}
    .signal-node {{ display: flex; flex-direction: column; align-items: center; width: 74px; flex: 0 0 auto; }}
    .signal-dot {{
        width: 14px; height: 14px; border-radius: 50%;
        border: 2px solid var(--skip); background: transparent; margin-bottom: 6px; box-sizing: border-box;
    }}
    .signal-dot.pending {{ border-color: var(--skip); }}
    .signal-dot.skipped {{ border-color: var(--skip); background: var(--skip); opacity: 0.5; }}
    .signal-dot.running {{
        border-color: var(--accent); background: var(--accent);
        animation: pulse 1.1s ease-in-out infinite;
    }}
    .signal-dot.done {{ border-color: var(--success); background: var(--success); }}
    .signal-dot.failed {{ border-color: var(--fail); background: var(--fail); }}

    @media (prefers-reduced-motion: reduce) {{ .signal-dot.running {{ animation: none; }} }}
    @keyframes pulse {{
        0% {{ box-shadow: 0 0 0 0 rgba(var(--accent-rgb), 0.5); }}
        70% {{ box-shadow: 0 0 0 6px rgba(var(--accent-rgb), 0); }}
        100% {{ box-shadow: 0 0 0 0 rgba(var(--accent-rgb), 0); }}
    }}

    .signal-code {{
        font-family: 'JetBrains Mono', monospace; font-size: 0.62rem; letter-spacing: 0.03em;
        color: var(--text); text-align: center; white-space: nowrap;
    }}
    .signal-node.skipped .signal-code, .signal-node.pending .signal-code {{ color: var(--text-muted); }}
    .signal-num {{ font-family: 'JetBrains Mono', monospace; font-size: 0.58rem; color: var(--text-muted); }}
    .signal-line {{ height: 2px; width: 20px; background: var(--skip); margin-top: -20px; flex: 0 0 auto; }}
    .signal-line.done {{ background: var(--success); }}
    .signal-line.running {{ background: var(--accent); }}

    .badge {{
        display: inline-block; font-family: 'JetBrains Mono', monospace; font-size: 0.72rem;
        padding: 0.15rem 0.55rem; border-radius: 999px; border: 1px solid var(--panel-border);
    }}
    .badge.success {{ color: var(--success); background: var(--success-soft); border-color: var(--success); }}
    .badge.fail {{ color: var(--fail); background: var(--fail-soft); border-color: var(--fail); }}
    .badge.info {{ color: var(--info); background: var(--bg-alt); border-color: var(--info); }}
    .badge.accent {{ color: var(--accent); background: var(--accent-soft); border-color: var(--accent); }}

    .gauge-wrap {{ display: flex; align-items: center; gap: 0.9rem; }}
    .gauge-value {{ font-family: 'Space Grotesk', sans-serif; font-size: 1.7rem; font-weight: 700; color: var(--text); }}
    .gauge-label {{
        color: var(--text-muted); font-size: 0.76rem; font-family: 'JetBrains Mono', monospace;
        text-transform: uppercase; letter-spacing: 0.08em;
    }}

    .stage-log-line {{
        font-size: 0.8rem; padding: 0.25rem 0; border-bottom: 1px dashed var(--panel-border); color: var(--text-muted);
    }}
    .stage-log-line .stage-code {{ color: var(--accent); margin-right: 0.5rem; }}

    .stButton > button, .stFormSubmitButton > button {{
        background: var(--accent) !important;
        color: var(--accent-text) !important;
        border: none !important;
        font-weight: 600;
        border-radius: 8px;
    }}
    .stButton > button:hover, .stFormSubmitButton > button:hover {{
        filter: brightness(1.08);
        color: var(--accent-text) !important;
    }}
    section[data-testid="stSidebar"] .stButton > button {{
        background: var(--panel);
        color: var(--text) !important;
        border: 1px solid var(--panel-border);
        font-weight: 500;
    }}
    section[data-testid="stSidebar"] .stButton > button:hover {{
        border-color: var(--accent);
        color: var(--accent) !important;
        background: var(--panel);
    }}

    [data-testid="stFormSubmitButton"] button {{
        padding: 0.5rem 1.3rem;
    }}

    .empty-state {{
        color: var(--text-muted); font-size: 0.88rem; padding: 1.4rem; text-align: center;
        border: 1px dashed var(--panel-border); border-radius: 10px;
    }}
    hr.console-divider {{ border: none; border-top: 1px solid var(--panel-border); margin: 1rem 0; }}

    .history-chip {{
        display: block; width: 100%; text-align: left; font-size: 0.8rem;
        padding: 0.35rem 0.55rem; margin-bottom: 0.3rem; border-radius: 6px;
        background: var(--panel); border: 1px solid var(--panel-border); color: var(--text-muted);
    }}
    """

    st.markdown(css, unsafe_allow_html=True)