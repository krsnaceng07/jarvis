"""jarvis.canvas.wrap — agent widget document wrapper.

OpenClaw parity: mirrors ``openclaw-main/src/canvas/wrap.ts``.

Builds the complete sandboxed HTML shell around agent-supplied widget_code:
  - Baked base styles (light/dark palette, design system helpers)
  - Size reporter bridge (postMessage height → embedding chat)
  - Prompt bridge (sendPrompt → openclaw:widget-prompt via MessageChannel)
  - Theme bridge (openclaw:widget-theme → CSS custom properties)
  - Snapshot bridge (openclaw:widget-snapshot-request → PNG data URL)
"""
from __future__ import annotations

import json
import re
from typing import Final

# ---------------------------------------------------------------------------
# Design system tokens (must match WIDGET_THEME_TOKENS in wrap.ts)
# ---------------------------------------------------------------------------

WIDGET_THEME_TOKENS: Final[list[str]] = [
    "surface",
    "card",
    "elevated",
    "text",
    "text-strong",
    "muted",
    "border",
    "border-strong",
    "accent",
    "accent-fill",
    "accent-fg",
    "ok",
    "warn",
    "danger",
    "info",
    "radius",
    "font-body",
    "font-mono",
]

# ---------------------------------------------------------------------------
# Baked palettes — mirrors WIDGET_BASE_STYLES in wrap.ts exactly.
# Light/dark values are sourced from ui/src/styles/base.css.
# ---------------------------------------------------------------------------

WIDGET_BASE_STYLES: Final[str] = (
    ":root{color-scheme:light dark;"
    "--surface:#faf9f7;--card:#ffffff;--elevated:#ffffff;"
    "--text:#403c35;--text-strong:#211e1a;--muted:#6e6960;"
    "--border:#e8e4dc;--border-strong:#d6d0c5;"
    "--accent:#bd4531;--accent-fill:#bd4531;--accent-fg:#ffffff;"
    "--ok:#15803d;--warn:#b45309;--danger:#dc2626;--info:#2563eb;"
    "--radius:10px;"
    "--font-body:-apple-system,BlinkMacSystemFont,\"Segoe UI\",Roboto,sans-serif;"
    "--font-mono:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;"
    "--accent-subtle:color-mix(in srgb,var(--accent) 10%,transparent);"
    "--ok-subtle:color-mix(in srgb,var(--ok) 10%,transparent);"
    "--warn-subtle:color-mix(in srgb,var(--warn) 12%,transparent);"
    "--danger-subtle:color-mix(in srgb,var(--danger) 10%,transparent);"
    "--info-subtle:color-mix(in srgb,var(--info) 10%,transparent)}"
    "@media (prefers-color-scheme:dark){:root{"
    "--surface:#0e1015;--card:#161920;--elevated:#191c24;"
    "--text:#d4d4d8;--text-strong:#f4f4f5;--muted:#8b8b94;"
    "--border:#1e2028;--border-strong:#2e3040;"
    "--accent:#ff5c5c;--accent-fill:#d13c3c;--accent-fg:#ffffff;"
    "--ok:#22c55e;--warn:#f59e0b;--danger:#ef4444;--info:#3b82f6}}"
    "*{box-sizing:border-box}html,body{margin:0}"
    "body{font:14px/1.5 var(--font-body);color:var(--text)}"
    "h1,h2,h3{margin:0 0 8px;color:var(--text-strong);font-weight:600}"
    "h1{font-size:18px}h2{font-size:16px}h3{font-size:14px}"
    "p{margin:0 0 8px}"
    "a{color:var(--accent)}"
    "button{font:13px var(--font-body);color:var(--text);background:var(--card);border:1px solid var(--border-strong);border-radius:var(--radius);padding:6px 14px;cursor:pointer}"
    "button:hover{border-color:var(--muted)}"
    "button.primary{background:var(--accent-fill);color:var(--accent-fg);border-color:transparent}"
    "input,select,textarea{font:13px var(--font-body);color:var(--text);background:var(--elevated);border:1px solid var(--border-strong);border-radius:var(--radius);padding:6px 10px}"
    "input:focus,select:focus,textarea:focus,button:focus-visible{outline:2px solid var(--accent);outline-offset:1px}"
    "table{border-collapse:collapse;width:100%;font-size:13px}"
    "th{text-align:left;font-weight:500;color:var(--muted);font-size:12px;padding:4px 8px}"
    "td{padding:6px 8px;border-top:1px solid var(--border)}"
    "code,pre{font-family:var(--font-mono);font-size:12px;background:var(--card);border-radius:4px}"
    "code{padding:1px 5px}pre{padding:10px;overflow-x:auto}"
    ".card{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);padding:14px}"
    ".badge{display:inline-block;font-size:12px;padding:2px 10px;border-radius:999px;background:var(--accent-subtle);color:var(--accent)}"
    ".badge.ok{background:var(--ok-subtle);color:var(--ok)}"
    ".badge.warn{background:var(--warn-subtle);color:var(--warn)}"
    ".badge.danger{background:var(--danger-subtle);color:var(--danger)}"
    ".badge.info{background:var(--info-subtle);color:var(--info)}"
    ".metric{font-size:24px;font-weight:600;color:var(--text-strong)}"
    ".muted{color:var(--muted)}"
    ".row{display:flex;gap:8px;align-items:center;flex-wrap:wrap}"
    ".svg-widget{display:grid;place-items:center}.svg-widget>svg{max-width:100%}"
)

# ---------------------------------------------------------------------------
# Bridge scripts — ported verbatim from wrap.ts
# ---------------------------------------------------------------------------

_SIZE_REPORTER: Final[str] = (
    "<script>(()=>{if(!window.parent||window.parent===window)return;"
    "let last=0;const report=()=>{const b=document.body;if(!b)return;"
    "const h=Math.ceil(Math.max(b.scrollHeight,b.offsetHeight,b.getBoundingClientRect().height));"
    'if(h&&h!==last){last=h;window.parent.postMessage({type:"openclaw:widget-size",height:h},"*");}};'
    "addEventListener('load',report);new ResizeObserver(report).observe(document.body);"
    "setTimeout(report,50);setTimeout(report,500);})();</script>"
)

_PROMPT_BRIDGE: Final[str] = (
    "<script>(()=>{if(!window.parent||window.parent===window)return;"
    "const c=new MessageChannel();"
    "const post=c.port1.postMessage.bind(c.port1);"
    "let act=null;"
    "try{const ua=navigator.userActivation;"
    'const d=ua&&Object.getOwnPropertyDescriptor(Object.getPrototypeOf(ua),"isActive");'
    "if(d&&d.get)act=d.get.bind(ua);}catch{}"
    'window.parent.postMessage({type:"openclaw:widget-prompt-offer"},"*",[c.port2]);'
    "window.sendPrompt=text=>{if(!act||act()!==true)return;"
    'post({type:"openclaw:widget-prompt",prompt:String(text)});};})();</script>'
)


def _build_theme_bridge() -> str:
    keys_json = json.dumps(WIDGET_THEME_TOKENS)
    return (
        "<script>(()=>{if(!window.parent||window.parent===window)return;"
        "const root=document.documentElement;const set=root.style.setProperty.bind(root.style);"
        "const rm=root.style.removeProperty.bind(root.style);"
        f"const keys={keys_json};"
        'addEventListener("message",event=>{if(event.source!==window.parent)return;'
        'const data=event.data;if(!data||data.type!=="openclaw:widget-theme"||'
        'typeof data.tokens!=="object"||data.tokens===null)return;'
        "for(const key of keys){const raw=data.tokens[key];"
        'const value=typeof raw==="string"?raw.trim():"";'
        'if(value&&value.length<=256)set("--"+key,value);else rm("--"+key);}'
        'if(data.mode==="light"||data.mode==="dark")set("color-scheme",data.mode);});})();</script>'
    )


# Snapshot bridge is long but ported verbatim from wrap.ts for security parity.
_SNAPSHOT_BRIDGE: Final[str] = (
    "<script>(()=>{if(!window.parent||window.parent===window)return;"
    "const parent=window.parent;const post=(message,origin)=>parent.postMessage(message,origin);"
    "const listen=window.addEventListener.bind(window);"
    "const clone=Node.prototype.cloneNode;const query=Element.prototype.querySelectorAll;"
    "const queryDocument=document.querySelectorAll.bind(document);"
    "const item=NodeList.prototype.item;const remove=Node.prototype.removeChild;"
    "const replace=Node.prototype.replaceChild;"
    'const getParent=Object.getOwnPropertyDescriptor(Node.prototype,"parentNode")?.get;'
    "const names=Element.prototype.getAttributeNames;const getAttr=Element.prototype.getAttribute;"
    "const setAttr=Element.prototype.setAttribute;"
    "const serializer=new XMLSerializer();const serialize=serializer.serializeToString.bind(serializer);"
    "const create=document.createElement.bind(document);const styles=getComputedStyle.bind(window);"
    "const getProperty=CSSStyleDeclaration.prototype.getPropertyValue;"
    "const getContext=HTMLCanvasElement.prototype.getContext;"
    "const toDataURL=HTMLCanvasElement.prototype.toDataURL;"
    'const setWidth=Object.getOwnPropertyDescriptor(HTMLCanvasElement.prototype,"width")?.set;'
    'const setHeight=Object.getOwnPropertyDescriptor(HTMLCanvasElement.prototype,"height")?.set;'
    'const setFill=Object.getOwnPropertyDescriptor(CanvasRenderingContext2D.prototype,"fillStyle")?.set;'
    "const fill=CanvasRenderingContext2D.prototype.fillRect;"
    "const draw=CanvasRenderingContext2D.prototype.drawImage;"
    "const add=EventTarget.prototype.addEventListener;const ImageCtor=Image;"
    'const setSrc=Object.getOwnPropertyDescriptor(HTMLImageElement.prototype,"src")?.set;'
    "const encode=encodeURIComponent;const P=Promise;const ErrorCtor=Error;const stringify=String;"
    "const max=Math.max.bind(Math);const min=Math.min.bind(Math);const ceil=Math.ceil.bind(Math);"
    'listen("message",event=>{if(event.source!==parent)return;'
    'const data=event.data;if(!data||data.type!=="openclaw:widget-snapshot-request"||typeof data.id!=="string")return;'
    "void (async()=>{try{const body=document.body;"
    "const width=max(1,body.scrollWidth);const height=max(1,body.scrollHeight);"
    'const root=clone.call(document.documentElement,true);const scripts=query.call(root,"script");'
    "for(let index=scripts.length-1;index>=0;index--){const script=item.call(scripts,index);"
    "if(script&&getParent){const owner=getParent.call(script);if(owner)remove.call(owner,script);}}"
    'const liveCanvases=queryDocument("canvas");const clonedCanvases=query.call(root,"canvas");'
    "for(let index=0;index<liveCanvases.length;index++){const live=item.call(liveCanvases,index);"
    "const cloned=item.call(clonedCanvases,index);if(!live||!cloned||!getParent||!setSrc)continue;"
    'const image=create("img");for(const name of names.call(cloned)){const value=getAttr.call(cloned,name);'
    "if(value!==null)setAttr.call(image,name,value);}setSrc.call(image,toDataURL.call(live,\"image/png\"));"
    "const owner=getParent.call(cloned);if(owner)replace.call(owner,image,cloned);}"
    "const svg='<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"'+width+'\" height=\"'+height+'\">"
    "<foreignObject width=\"100%\" height=\"100%\">'+serialize(root)+'</foreignObject></svg>';"
    "const url=\"data:image/svg+xml;charset=utf-8,\"+encode(svg);"
    "const image=new ImageCtor();await new P((resolve,reject)=>{"
    'add.call(image,"load",resolve,{once:true});add.call(image,"error",()=>reject(new ErrorCtor("widget snapshot image failed to load")),{once:true});'
    "if(!setSrc)throw new ErrorCtor(\"widget snapshot image source unavailable\");setSrc.call(image,url);});"
    "const canvas=create(\"canvas\");const scale=min(window.devicePixelRatio||1,2);"
    "if(!setWidth||!setHeight)throw new ErrorCtor(\"widget snapshot canvas dimensions unavailable\");"
    "const canvasWidth=ceil(width*scale);const canvasHeight=ceil(height*scale);"
    "if(canvasWidth>16384||canvasHeight>16384||canvasWidth*canvasHeight>16777216)throw new ErrorCtor(\"widget snapshot dimensions exceed limit\");"
    "setWidth.call(canvas,canvasWidth);setHeight.call(canvas,canvasHeight);"
    "const context=getContext.call(canvas,\"2d\");if(!context||!setFill)throw new ErrorCtor(\"widget snapshot canvas unavailable\");"
    "setFill.call(context,getProperty.call(styles(document.documentElement),\"--surface\"));"
    "fill.call(context,0,0,canvasWidth,canvasHeight);draw.call(context,image,0,0,canvasWidth,canvasHeight);"
    'post({type:"openclaw:widget-snapshot",id:data.id,dataUrl:toDataURL.call(canvas,"image/png"),width,height},"*");'
    '}catch(error){post({type:"openclaw:widget-snapshot",id:data.id,error:stringify(error)},"*");}})();});})();</script>'
)

# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

_SVG_RE = re.compile(r"^<svg\b", re.IGNORECASE)


def _escape_html(value: str) -> str:
    return (
        value
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def build_widget_document(title: str, widget_code: str) -> str:
    """Wrap agent-supplied widget markup in the stable isolated Canvas document shell.

    OpenClaw parity: mirrors ``buildWidgetDocument`` in ``wrap.ts``.
    Document structure (order matches OpenClaw exactly):
        <head>: charset, viewport, CSP, title, base styles
        <body>: prompt bridge, theme bridge, snapshot bridge, widget_code, size reporter
    """
    is_svg = bool(_SVG_RE.match(widget_code))
    body_class = ' class="svg-widget"' if is_svg else ""
    theme_bridge = _build_theme_bridge()

    return (
        "<!doctype html>"
        "<html><head>"
        '<meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta http-equiv="Content-Security-Policy" '
        'content="default-src \'none\'; style-src \'unsafe-inline\'; '
        'script-src \'unsafe-inline\'; img-src data:;">'
        f"<title>{_escape_html(title)}</title>"
        f"<style>{WIDGET_BASE_STYLES}</style>"
        "</head>"
        f"<body{body_class}>"
        f"{_PROMPT_BRIDGE}"
        f"{theme_bridge}"
        f"{_SNAPSHOT_BRIDGE}"
        f"{widget_code}"
        f"{_SIZE_REPORTER}"
        "</body></html>"
    )


__all__ = [
    "WIDGET_BASE_STYLES",
    "WIDGET_THEME_TOKENS",
    "build_widget_document",
]
