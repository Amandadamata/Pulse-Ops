"""Gera o material de estudo (HTML e PDF) a partir de study/fonte/.

Uso:
    python3 study/build.py            # HTML + PDF em study/build/ e cópia em docs/estudo/
    python3 study/build.py --html     # só HTML (sem Chromium)

Diretivas aceitas nos arquivos .md (cada uma sozinha na linha):
    @@trecho caminho/do/arquivo.py 10-25   -> linhas 10 a 25, numeradas como no arquivo
    @@arquivo caminho/do/arquivo.py        -> o arquivo inteiro, numerado
    @@diagrama nome                        -> study/diagramas/nome.svg
    @@sql nome                             -> study/sql/nome.sql (SQL capturado dos testes)
Marcadores de texto: {{COMMIT}}, {{COMMIT_CURTO}}, {{DATA}}, {{VERSAO}}.

Os trechos são lidos dos arquivos do repositório no momento do build. Para evitar
que o texto explique uma versão e o código mostre outra, o build falha se algum
arquivo de código mudou desde o commit registrado em study/commit-explicado.txt.

Requisitos: Python 3, git, pandoc (3.x) e, para o PDF, Node com o pacote
"playwright" e Chromium (study/imprimir.mjs).
"""

import argparse
import datetime
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STUDY = ROOT / "study"
BUILD = STUDY / "build"
OUTPUT = ROOT / "docs" / "estudo"
VERSION = "1.0"
CODE_PATHS = [
    "src",
    "lab",
    "scripts",
    "tests",
    "migrations",
    "Dockerfile",
    "compose.yaml",
    "compose.demo.yaml",
    ".github",
    "pyproject.toml",
    "alembic.ini",
    ".env.example",
]
LANGUAGES = {
    ".py": "python",
    ".html": "html",
    ".css": "css",
    ".js": "javascript",
    ".mjs": "javascript",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
    ".ini": "ini",
    ".sh": "bash",
    ".md": "markdown",
    "Dockerfile": "dockerfile",
    ".example": "bash",
}
VOLUMES = {
    "volume-1": "PulseOps por dentro: guia de código, decisões e preparação para entrevistas",
    "volume-2": "PulseOps por dentro — Volume 2: código explicado linha a linha",
}


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout.strip()


def explained_commit() -> str:
    commit = (STUDY / "commit-explicado.txt").read_text().strip()
    full = git("rev-parse", commit)
    changed = git("diff", "--name-only", full, "HEAD", "--", *CODE_PATHS)
    dirty = git("status", "--porcelain", "--", *CODE_PATHS)
    if changed or dirty:
        sys.exit(
            "O código mudou desde o commit explicado; revise os trechos e atualize "
            f"study/commit-explicado.txt.\nArquivos:\n{changed}\n{dirty}"
        )
    return full


def language_of(path: Path) -> str:
    return LANGUAGES.get(path.name) or LANGUAGES.get(path.suffix, "text")


def code_block(relative: str, first: int | None, last: int | None, where: str) -> str:
    path = ROOT / relative
    if not path.is_file():
        sys.exit(f"{where}: arquivo inexistente {relative}")
    lines = path.read_text(encoding="utf-8").splitlines()
    first = first or 1
    last = last or len(lines)
    if not 1 <= first <= last <= len(lines):
        sys.exit(f"{where}: intervalo {first}-{last} fora de {relative} ({len(lines)} linhas)")
    body = "\n".join(lines[first - 1 : last])
    fence = "````" if "```" in body else "```"
    title = relative if (first, last) == (1, len(lines)) else f"{relative}, linhas {first}–{last}"
    return (
        f'\n<div class="trecho-titulo">{title}</div>\n\n'
        f'{fence}{{.{language_of(path)} .numberLines startFrom="{first}"}}\n{body}\n{fence}\n'
    )


SQL_BREAKS = re.compile(
    r" (?=(FROM|WHERE|AND|ORDER BY|GROUP BY|LIMIT|FOR UPDATE|ON CONFLICT|RETURNING|JOIN|VALUES) )"
)


def sql_block(name: str, where: str) -> str:
    """SQL capturado por study/captura_sql.py. Só quebra linhas antes de palavras-chave;
    o texto do comando não é alterado."""
    path = STUDY / "sql" / f"{name}.sql"
    if not path.is_file():
        sys.exit(f"{where}: SQL não capturado {path} (rode study/captura_sql.py)")
    lines = [" ".join(line.split()) for line in path.read_text(encoding="utf-8").splitlines()]
    body = SQL_BREAKS.sub("\n  ", " ".join(lines))
    title = f'<div class="trecho-titulo">SQL enviado ao PostgreSQL: {name}</div>'
    return f"\n{title}\n\n```sql\n{body}\n```\n"


def expand(text: str, where: str, replacements: dict[str, str]) -> str:
    out = []
    for number, line in enumerate(text.splitlines(), 1):
        place = f"{where}:{number}"
        if line.startswith("@@trecho "):
            _, relative, span = line.split()
            first, _, last = span.partition("-")
            out.append(code_block(relative, int(first), int(last or first), place))
        elif line.startswith("@@arquivo "):
            out.append(code_block(line.split()[1], None, None, place))
        elif line.startswith("@@sql "):
            out.append(sql_block(line.split()[1], place))
        elif line.startswith("@@diagrama "):
            name = line.split()[1]
            svg = STUDY / "diagramas" / f"{name}.svg"
            if not svg.exists():
                sys.exit(f"{place}: diagrama inexistente {svg}")
            out.append(f'\n<div class="diagrama">{svg.read_text(encoding="utf-8")}</div>\n')
        else:
            for key, value in replacements.items():
                line = line.replace(key, value)
            out.append(line)
    return "\n".join(out) + "\n"


def build_volume(name: str, title: str, replacements: dict[str, str]) -> Path:
    sources = sorted((STUDY / "fonte" / name).glob("*.md"))
    combined = "\n\n".join(
        expand(s.read_text(encoding="utf-8"), s.relative_to(ROOT).as_posix(), replacements)
        for s in sources
    )
    BUILD.mkdir(exist_ok=True)
    markdown = BUILD / f"{name}.md"
    markdown.write_text(combined, encoding="utf-8")
    html = BUILD / f"{name}.html"
    subprocess.run(
        [
            "pandoc",
            str(markdown),
            "--from",
            "markdown+smart",
            "--to",
            "html5",
            "--standalone",
            "--toc",
            "--toc-depth=2",
            *(["--number-sections"] if name == "volume-1" else []),  # o volume 2 usa D1, D2...
            "--highlight-style",
            "tango",
            "--css",
            "estilo.css",
            "--metadata",
            f"title={title}",
            "--metadata",
            "lang=pt-BR",
            "--output",
            str(html),
        ],
        check=True,
    )
    return html


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--html", action="store_true", help="não gera PDF")
    args = parser.parse_args()

    commit = explained_commit()
    replacements = {
        "{{COMMIT}}": commit,
        "{{COMMIT_CURTO}}": commit[:7],
        "{{DATA}}": datetime.datetime.now(datetime.UTC).date().isoformat(),
        "{{VERSAO}}": VERSION,
    }
    BUILD.mkdir(exist_ok=True)
    shutil.copy(STUDY / "estilo.css", BUILD / "estilo.css")
    pages = [build_volume(name, title, replacements) for name, title in VOLUMES.items()]
    if args.html:
        print("HTML:", *pages)
        return 0
    pdfs = [page.with_suffix(".pdf") for page in pages]
    for page, pdf in zip(pages, pdfs, strict=True):
        subprocess.run(["node", str(STUDY / "imprimir.mjs"), str(page), str(pdf)], check=True)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for pdf in pdfs:
        shutil.copy(pdf, OUTPUT / f"pulseops-por-dentro-{pdf.stem}.pdf")
    print("PDF:", *(OUTPUT / f"pulseops-por-dentro-{p.stem}.pdf" for p in pdfs))
    return 0


if __name__ == "__main__":
    sys.exit(main())
