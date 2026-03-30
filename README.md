# fontconvert

A command-line tool that builds TTF and OTF fonts from SVG glyph artwork via a
[UFO](https://unifiedfontobject.org/) pipeline, powered by
[fontmake](https://github.com/googlefonts/fontmake) and
[ufoLib2](https://github.com/fonttools/ufoLib2).

## Features

- Build **TTF** and/or **OTF** fonts directly from SVG files
- Two input modes: per-glyph SVG files in a directory, or a single combined SVG
- Monospace-first: optional fixed advance width for every glyph
- Full printable ASCII character set by default (U+0020 – U+007E)
- Simple YAML manifest for font metadata and build settings

## Requirements

- Python >= 3.10
- [fontmake](https://github.com/googlefonts/fontmake) (installed automatically as a dependency)

## Installation

Install the package (and its dependencies) from the project root:

```bash
pip install .
```

This installs the `fontconvert` command. If the installed script is not on your
`PATH` (a common situation on Windows), you can invoke the tool as a module
instead:

```bash
python -m fontconvert build
```

## Quick Start

1. Create your glyph SVGs (see [SVG Inputs](#svg-inputs) below).
2. Edit `glyphs/manifest.yaml` to set your family name and style (see
   [Manifest](#manifest-manifestyaml)).
3. Run the build:

```bash
fontconvert build
```

Output fonts are written to `dist/` by default.

## CLI Reference

```
fontconvert build [OPTIONS]
```

| Option | Default | Description |
|---|---|---|
| `--manifest PATH` | `glyphs/manifest.yaml` | Path to the manifest YAML file |
| `--mapping PATH` | `ASCII_MAPPING.tsv` | Path to the glyph-to-codepoint mapping TSV |
| `--out-dir PATH` | `dist` | Directory where built fonts are written |
| `--ttf` | *(default when neither flag is set)* | Build a TTF font |
| `--otf` | | Also build an OTF font |

### Examples

```bash
# Build TTF (default)
fontconvert build

# Build both TTF and OTF
fontconvert build --otf

# Custom paths
fontconvert build --manifest my_project/manifest.yaml --out-dir output/
```

## Manifest (`manifest.yaml`)

The manifest controls font metadata and how SVG inputs are located.

```yaml
family_name: "My Font"
style_name: "Regular"
units_per_em: 2048

# Input mode: "directory" (one SVG per glyph) or "combined" (single SVG file)
mode: "directory"

inputs:
  directory:
    svg_dir: "svg"          # relative to the manifest file
  combined:
    svg_file: "combined/font.svg"

monospace:
  enabled: true
  advance_width: 600        # advance width applied to every glyph

# Reserved for future explicit glyph overrides; leave empty to use all
# codepoints in ASCII_MAPPING.tsv
glyphs: []
```

### Fields

| Field | Default | Description |
|---|---|---|
| `family_name` | `"Untitled Font"` | Font family name |
| `style_name` | `"Regular"` | Style / weight name |
| `units_per_em` | `1000` | UPM (units per em) |
| `mode` | `"directory"` | `"directory"` or `"combined"` |
| `inputs.directory.svg_dir` | `"svg"` | Directory containing per-glyph SVG files |
| `inputs.combined.svg_file` | `"combined/font.svg"` | Path to the combined SVG file |
| `monospace.enabled` | `true` | Apply a fixed advance width to all glyphs |
| `monospace.advance_width` | `600` | The fixed advance width (in UPM units) |

## SVG Inputs

### Directory mode (`mode: "directory"`)

Place one SVG file per glyph inside `svg_dir`. Each file must be named after the
glyph's PostScript name as listed in `ASCII_MAPPING.tsv`:

```
glyphs/
  svg/
    A.svg
    B.svg
    space.svg
    exclam.svg
    ...
```

### Combined mode (`mode: "combined"`)

Place all glyphs inside a single SVG file. Each glyph is wrapped in a `<g>`
element whose `id` attribute matches the PostScript glyph name:

```xml
<svg xmlns="http://www.w3.org/2000/svg" version="1.1">
  <g id="A"> ... </g>
  <g id="B"> ... </g>
  <g id="space"> ... </g>
</svg>
```

## ASCII Mapping (`ASCII_MAPPING.tsv`)

`ASCII_MAPPING.tsv` maps every glyph name to its Unicode codepoint. The default
file covers the full printable ASCII range (U+0020 – U+007E, 95 characters). The format is a tab-separated file with three columns:

```
glyph_name    codepoint_hex    char
space         0020              
exclam        0021             !
...
```

You can supply a custom mapping file with `--mapping`.

## Project Layout

```
fontconvert/
├── glyphs/
│   └── manifest.yaml       # build configuration
├── src/
│   └── fontconvert/
│       ├── __init__.py
│       ├── build.py        # core build pipeline
│       ├── cli.py          # CLI entry point
│       └── manifest.py     # manifest loader
├── ASCII_MAPPING.tsv       # default glyph-to-codepoint table
└── pyproject.toml
```

## License

See [LICENSE](LICENSE) if present, or contact the project maintainers.
