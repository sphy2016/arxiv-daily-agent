# Research interests

_This is a living memory file. You edit it, and so do `./run.sh interest "..."` and the weekly consolidation from your feedback.
`./data-git log -p memory/interests.md` shows how your interests have changed over time._

## Pinned (never removed automatically)
- High-redshift galaxies (z ≳ 5), especially JWST-era discoveries and population statistics
- Reionization: sources, timeline, topology, IGM neutral fraction, ionized bubbles
- Lyman continuum (LyC) escape: direct detections, escape fractions, indirect tracers, low-z LyC-leaker analogs (green peas, LzLCS)
- Lyman-α emission and transmission as probes of galaxies and of reionization (LAEs, Lyα fractions, Lyα luminosity functions, line profiles)
- Galaxy formation and assembly: stellar-mass build-up, early massive and quiescent galaxies, morphology and size evolution, mergers
- Large survey data releases and catalogs: JWST, HST, Roman, Euclid, and large ground-based facilities (Subaru HSC/PFS, VLT/MUSE, Keck, DESI, ALMA, Rubin/LSST, ELTs)

## Current focus (adjusted automatically from feedback)
- (nothing yet; this section fills in as you rate papers)

## Less interested / avoid
- (nothing yet)

## Scoring guidance
- 9–10: central to reionization, LyC, or Lyα at high z; a major JWST/HST/Euclid/Roman or large ground-based data release or catalog
- 7–8: properties or statistics of high-z galaxies; galaxy assembly with a clear high-z angle; low-z LyC/Lyα analogs; new survey methods or pipelines for these facilities
- 4–6: galaxy evolution at cosmic noon or lower z without a high-z or reionization link; related theory or simulations only loosely tied to observations
- 0–3: Milky Way and local-group stellar physics, ISM microphysics, and anything unrelated

## Matching profile
The fast keyword pre-filter uses this block. The keys are case-insensitive regexes.
Keep it valid TOML.

```toml
categories = ["astro-ph.GA", "astro-ph.CO", "astro-ph.IM"]
authors = []          # e.g. ["Robertson", "Naidu"]; a match adds a large bonus

[keywords]
'reioni[sz]' = 4
'epoch of reionization|\bEoR\b' = 4
'lyman[- ]continuum|\bLyC\b' = 4
'escape fraction|f_?\{?esc' = 3
'ionizing (photon|emissivity|budget)|ionising' = 3
'lyman[- ]?(alpha|α)|ly\s?(α|alpha|\\alpha)|\bLAEs?\b' = 4
'neutral (hydrogen )?fraction|ionized bubble|damping wing' = 3
'high[- ]redshift|high[- ]z\b|cosmic dawn|first galaxies' = 3
'z\s*(=|~|>|≳|≈|\\sim|\\gtrsim|\\approx|\\simeq)\s*(\$\s*)?([5-9]|1[0-9])' = 3
'\bJWST\b|NIRSpec|NIRCam|MIRI|NIRISS' = 2
'\bHST\b|Hubble' = 1
'\bEuclid\b' = 2
'\bRoman\b' = 2
'data release|\bDR\d\b|catalog(ue)?s? (release|of)|public release' = 3
'HSC|Subaru|\bPFS\b|MUSE|\bKeck\b|\bDESI\b|\bALMA\b|Rubin|LSST|\bELT\b' = 1
'galaxy (formation|assembly|evolution)|stellar mass (function|assembly|build)' = 2
'UV luminosity function|\bUVLF\b|star formation rate density' = 2
'(massive|quiescent) galaxies at|little red dots|\bLRDs?\b' = 2
'green pea|LzLCS|Lyman break' = 2
'Pop(ulation)? ?III' = 2

[negative]
'Milky Way|Galactic (disk|plane|center|centre)|solar neighbo' = 3
'globular cluster|open cluster|molecular cloud core' = 2
```
