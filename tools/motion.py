# PowerPoint motion written straight into slide XML, since python-pptx has no animation API:
# Morph between slides, entrance effects that play on their own as a slide opens, and a film
# that starts by itself. Checked in PowerPoint: every effect loads and plays in order.

import itertools

from lxml import etree

P = "http://schemas.openxmlformats.org/presentationml/2006/main"
# Morph between slides; a plain fade where Morph is not available.
MORPH = (
    '<mc:AlternateContent xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006">'
    '<mc:Choice xmlns:p159="http://schemas.microsoft.com/office/powerpoint/2015/09/main" '
    f'Requires="p159"><p:transition xmlns:p="{P}" xmlns:p14="http://schemas.microsoft.com/office/'
    'powerpoint/2010/main" spd="slow" p14:dur="900"><p159:morph option="byObject"/></p:transition>'
    f'</mc:Choice><mc:Fallback><p:transition xmlns:p="{P}" spd="slow"><p:fade/></p:transition>'
    "</mc:Fallback></mc:AlternateContent>"
)
# Entrance effects as PowerPoint names them (preset, subtype) and how long each takes, in ms.
EFFECTS = dict(fade=(10, 0, 600), wipe=(22, 8, 1000), zoom=(53, 16, 600), rise=(42, 0, 700))
MOVES = dict(
    zoom=[("ppt_w", "0", "#ppt_w"), ("ppt_h", "0", "#ppt_h")],
    rise=[("ppt_y", "#ppt_y+0.1", "#ppt_y")],
)


# One entrance effect's behaviours: shown, faded or wiped in, and grown or lifted into place.
def behaviours(effect: str, spid: int, ids) -> str:
    target = f'<p:tgtEl><p:spTgt spid="{spid}"/></p:tgtEl>'
    duration = EFFECTS[effect][2]
    out = (
        f'<p:set><p:cBhvr><p:cTn id="{next(ids)}" dur="1" fill="hold"><p:stCondLst><p:cond '
        f'delay="0"/></p:stCondLst></p:cTn>{target}<p:attrNameLst><p:attrName>style.visibility'
        '</p:attrName></p:attrNameLst></p:cBhvr><p:to><p:strVal val="visible"/></p:to></p:set>'
        f'<p:animEffect transition="in" filter="{"wipe(left)" if effect == "wipe" else "fade"}">'
        f'<p:cBhvr><p:cTn id="{next(ids)}" dur="{duration}"/>{target}</p:cBhvr></p:animEffect>'
    )
    for attr, start, end in MOVES.get(effect, []):
        out += (
            f'<p:anim calcmode="lin" valueType="num"><p:cBhvr additive="base"><p:cTn '
            f'id="{next(ids)}" dur="{duration}" fill="hold"/>{target}<p:attrNameLst><p:attrName>'
            f'{attr}</p:attrName></p:attrNameLst></p:cBhvr><p:tavLst><p:tav tm="0"><p:val>'
            f'<p:strVal val="{start}"/></p:val></p:tav><p:tav tm="100000"><p:val><p:strVal '
            f'val="{end}"/></p:val></p:tav></p:tavLst></p:anim>'
        )
    return out


# The slide's timeline: each (shape, effect, start in ms) plays on its own as the slide opens,
# and a film, if any, starts playing by itself.
def timeline(steps, film=None) -> str:
    ids, pars, builds = itertools.count(4), [], []

    def par(attrs: str, start: int, body) -> str:
        outer, inner = next(ids), next(ids)
        return (
            f'<p:par><p:cTn id="{outer}" fill="hold"><p:stCondLst><p:cond delay="{start}"/>'
            f'</p:stCondLst><p:childTnLst><p:par><p:cTn id="{inner}" {attrs} fill="hold" '
            'nodeType="afterEffect"><p:stCondLst><p:cond delay="0"/></p:stCondLst><p:childTnLst>'
            f"{body()}</p:childTnLst></p:cTn></p:par></p:childTnLst></p:cTn></p:par>"
        )

    for item, effect, start in steps:
        preset, subtype, _ = EFFECTS[effect]
        text = ' grpId="0"' if item.has_text_frame else ""
        attrs = f'presetID="{preset}" presetClass="entr" presetSubtype="{subtype}"{text}'
        pars.append(par(attrs, start, lambda: behaviours(effect, item.shape_id, ids)))
        if text:
            builds.append(f'<p:bldP spid="{item.shape_id}" grpId="0" animBg="1"/>')
    media = ""
    if film is not None:
        target = f'<p:tgtEl><p:spTgt spid="{film.shape_id}"/></p:tgtEl>'

        def play() -> str:
            return (
                f'<p:cmd type="call" cmd="playFrom(0.0)"><p:cBhvr><p:cTn id="{next(ids)}" '
                f'dur="90000" fill="hold"/>{target}</p:cBhvr></p:cmd>'
            )

        pars.append(par('presetID="1" presetClass="mediacall" presetSubtype="0"', 0, play))
        media = (
            f'<p:video><p:cMediaNode vol="80000"><p:cTn id="{next(ids)}" fill="hold" display="0">'
            '<p:stCondLst><p:cond delay="indefinite"/></p:stCondLst><p:endCondLst><p:cond '
            'evt="onStopAudio" delay="0"><p:tgtEl><p:sldTgt/></p:tgtEl></p:cond></p:endCondLst>'
            f"</p:cTn>{target}</p:cMediaNode></p:video>"
        )
    cond = '<p:cond evt="{}" delay="0"><p:tgtEl><p:sldTgt/></p:tgtEl></p:cond>'
    return (
        f'<p:timing xmlns:p="{P}"><p:tnLst><p:par><p:cTn id="1" dur="indefinite" '
        'restart="never" nodeType="tmRoot"><p:childTnLst><p:seq concurrent="1" nextAc="seek">'
        '<p:cTn id="2" dur="indefinite" nodeType="mainSeq"><p:childTnLst><p:par><p:cTn id="3" '
        'fill="hold"><p:stCondLst><p:cond delay="indefinite"/><p:cond evt="onBegin" delay="0">'
        f'<p:tn val="2"/></p:cond></p:stCondLst><p:childTnLst>{"".join(pars)}</p:childTnLst>'
        f"</p:cTn></p:par></p:childTnLst></p:cTn><p:prevCondLst>{cond.format('onPrev')}"
        f"</p:prevCondLst><p:nextCondLst>{cond.format('onNext')}</p:nextCondLst></p:seq>"
        f"{media}</p:childTnLst></p:cTn></p:par></p:tnLst>"
        + (f"<p:bldLst>{''.join(builds)}</p:bldLst>" if builds else "")
        + "</p:timing>"
    )


# Morph into this slide, play its timeline, and what to say over it in the speaker notes.
def finish(page, notes: str = "", steps=(), film=None) -> None:
    sld = page._element
    after = sld.find(f"{{{P}}}clrMapOvr")
    at = list(sld).index(after) + 1 if after is not None else 1
    sld.insert(at, etree.fromstring(MORPH))
    old = sld.find(f"{{{P}}}timing")
    if old is not None:
        sld.remove(old)
    if steps or film is not None:
        sld.insert(at + 1, etree.fromstring(timeline(steps, film)))
    if notes:
        page.notes_slide.notes_text_frame.text = notes


# Shapes one after another with the same effect, `gap` ms apart.
def stagger(items, effect: str, start: int = 0, gap: int = 150) -> list:
    return [(item, effect, start + gap * i) for i, item in enumerate(items)]


# Every shape a call adds to the slide, so a table drawn elsewhere can be animated as it lands.
def added(page, draw, *args) -> list:
    before = len(page.shapes)
    draw(page, *args)
    return list(page.shapes)[before:]
