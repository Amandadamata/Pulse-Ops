"""Confere se os testes e arquivos citados na documentação existem de verdade.

Procura, em docs/*.md e README.md, referências como `tests/x.py::test_y`, as formas
abreviadas `::test_z` e `test_z` (que herdam o último arquivo citado na mesma linha) e caminhos
de arquivos do repositório entre crases. Sai com código 1 se algo não existir.
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOKEN = re.compile(r"`([^`\s]+)`")
PATH_PREFIXES = ("tests/", "src/", "scripts/", "docs/", "lab/", "migrations/", ".github/")


def main() -> int:
    documents = [ROOT / "README.md", ROOT / "CLAUDE.md", *sorted((ROOT / "docs").rglob("*.md"))]
    problems: list[str] = []
    checked = 0
    for doc in documents:
        if not doc.exists() or doc.name == "especificacao.md":
            continue
        for number, line in enumerate(doc.read_text(encoding="utf-8").splitlines(), 1):
            current: Path | None = None
            for token in TOKEN.findall(line):
                file_part, _, test = token.partition("::")
                if file_part.startswith(PATH_PREFIXES):
                    path = ROOT / file_part.rstrip("/")
                    if "*" in file_part or "{" in file_part:
                        continue
                    checked += 1
                    if not path.exists():
                        problems.append(f"{doc.name}:{number}: arquivo inexistente {file_part}")
                        continue
                    current = path if path.suffix == ".py" else None
                elif file_part == "" and test:
                    pass  # forma abreviada; usa o arquivo atual
                elif re.fullmatch(r"test_\w+", token) and current is not None:
                    test = token  # nome solto depois de um arquivo citado na mesma linha
                else:
                    continue
                if test:
                    checked += 1
                    if current is None:
                        problems.append(f"{doc.name}:{number}: ::{test} sem arquivo antes")
                    elif not re.search(rf"def {re.escape(test)}\b", current.read_text()):
                        problems.append(f"{doc.name}:{number}: {test} não existe em {current.name}")
    for problem in problems:
        print(problem)
    print(f"{checked} referências conferidas, {len(problems)} problemas")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
