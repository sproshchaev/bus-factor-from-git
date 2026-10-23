"""Выгрузка истории git одного проекта в data/<name>.tsv.

Имена и адреса разработчиков в файл не попадают: после склейки псевдонимов
каждый человек получает номер d0001, d0002, ... в порядке первого появления.

    python3 extract.py <путь к клону> <имя> <sha>
"""
import re
import subprocess
import sys

# Файлы кода, которые считаем. Сторонний и сгенерированный код отбрасываем.
SRC = re.compile(r"\.(java|kt|kts|py|go|js|ts|scala|groovy|c|h|cpp|rs|rb|php|swift)$")
SKIP = re.compile(r"(^|/)(vendor|node_modules|third_party|generated|build)/")
BOT = re.compile(r"\[bot\]|dependabot|renovate|github-actions|pre-commit-ci", re.I)
# Соавтор из трейлера вида Co-...-by: Имя <адрес>
TRAILER = re.compile(r"^co-[a-z]+-by:[ \t]*(.*?)[ \t]*<([^>]+)>[ \t]*$", re.I | re.M)


def is_agent(name, email):
    """Не человек и не служебный бот: агент, который пишет код."""
    local = email.partition("@")[0]
    if local == "noreply":
        return True
    return "agent" in name.lower() or "agent" in local.lower()


def git(repo, *args):
    return subprocess.run(["git", "-C", repo, *args], capture_output=True,
                          text=True, check=True).stdout


def lev1(a, b):
    """Расстояние Левенштейна не больше единицы."""
    if a == b:
        return True
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b)) <= 1
    if len(a) > len(b):
        a, b = b, a
    i = j = skips = 0
    while i < len(a) and j < len(b):
        if a[i] != b[j]:
            skips += 1
            j += 1
            if skips > 1:
                return False
        else:
            i += 1
            j += 1
    return True


class Aliases:
    """Склейка псевдонимов: общий адрес или имя с отличием в одну букву."""

    def __init__(self):
        self.parent = {}

    def find(self, x):
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a, b):
        self.parent[self.find(a)] = self.find(b)


def numbering(fmt):
    """Номер по первому появлению ключа: d0001, d0002, ..."""
    ids = {}
    return lambda key: ids.setdefault(key, fmt % (len(ids) + 1))


def read_commits(repo, sha):
    raw = git(repo, "-c", "diff.renameLimit=10000", "log", "--no-merges", "-M",
              "--name-status", "--format=@@%x1f%an%x1f%ae%x1f%cs%x1f%B%x1e", sha)
    commits = []
    for chunk in raw.split("@@\x1f")[1:]:
        meta, _, body = chunk.partition("\x1e")
        name, email, date, msg = meta.split("\x1f", 3)
        changes = [line.split("\t") for line in body.strip().splitlines() if line.strip()]
        co = [(n, e.lower()) for n, e in TRAILER.findall(msg)]
        commits.append(dict(email=email.lower(), date=date, co=co, changes=changes,
                            people=[(name, email.lower())] + co))
    return commits


def main(repo, name, sha):
    commits = read_commits(repo, sha)
    al = Aliases()
    names = set()
    for c in commits:
        for n, e in c["people"]:
            al.union("e:" + e, "n:" + n.lower())
            names.add(n.lower())
    long_names = [n for n in sorted(names) if len(n) > 4]
    for i, a in enumerate(long_names):
        for b in long_names[i + 1:]:
            if lev1(a, b):
                al.union("n:" + a, "n:" + b)

    kind = {}
    for c in commits:
        for n, e in c["people"]:
            root = al.find("e:" + e)
            if is_agent(n, e):
                kind[root] = "a"
            elif BOT.search(n + " " + e):
                kind.setdefault(root, "b")
    # Люди и пути получают номера в порядке первого появления:
    # для расчёта важна только их идентичность.
    dev, pid = numbering("d%04d"), numbering("f%06d")
    kind_of = lambda e: kind.get(al.find("e:" + e), "h")

    is_src = lambda p: SRC.search(p) and not SKIP.search(p)
    files = [f for f in git(repo, "ls-tree", "-r", "--name-only", sha).splitlines() if is_src(f)]
    head_date = git(repo, "show", "-s", "--format=%cs", sha).strip()
    out = ["#\t%s\t%s\t%s" % (name, sha, head_date)]
    out += ["F\t" + pid(f) for f in files]
    for c in commits:
        d, k = dev(al.find("e:" + c["email"])), kind_of(c["email"])
        agent_co = any(kind_of(e) == "a" for _, e in c["co"])
        out.append("C\t%s\t%s\t%s\t%d" % (c["date"], d, k, agent_co))
        # Все изменения, а не только код: файл мог раньше называться иначе.
        out += ["\t".join([ch[0]] + [pid(p) for p in ch[1:]]) for ch in c["changes"]]
    with open("data/%s.tsv" % name, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(out) + "\n")


if __name__ == "__main__":
    main(*sys.argv[1:4])
