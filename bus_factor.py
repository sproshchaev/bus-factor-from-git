"""Truck factor по истории git и доля кода, у которой не осталось автора.

Метод авторства и алгоритм truck factor: Avelino, Passos, Hora, Valente,
"A Novel Approach for Estimating Truck Factors", ICPC 2016, arXiv:1604.06766.

    python3 bus_factor.py data/*.tsv
"""
import math
import sys
from collections import defaultdict
from datetime import date, timedelta

DOA_MIN = 3.293     # абсолютный порог DOA (m в статье)
DOA_SHARE = 0.75    # порог нормированного DOA (k в статье)
COVERAGE = 0.5      # проект в беде, когда авторы покрывают меньше половины файлов
ACTIVE_DAYS = 365   # активен тот, кто коммитил за последний год до HEAD
WINDOWS = (180, 365, 730)  # проверка устойчивости: другое окно активности


def load(path):
    name = head = None
    files, commits = [], []
    with open(path, encoding="utf-8") as f:
        for line in f:
            p = line.rstrip("\n").split("\t")
            if p[0] == "#":
                name, head = p[1], p[3]
            elif p[0] == "F":
                files.append(p[1])
            elif p[0] == "C":
                commits.append(dict(date=p[1], dev=p[2], kind=p[3], agent_co=p[4] == "1", changes=[]))
            else:
                commits[-1]["changes"].append(p)
    if name is None or not files or not commits:
        sys.exit("%s: нет заголовка, файлов кода или коммитов" % path)
    return name, head, files, commits


def trace(files, commits):
    """История каждого файла HEAD с учётом переименований, от новых коммитов к старым."""
    alive = {f: f for f in files}
    first, deliveries, total = {}, defaultdict(lambda: defaultdict(int)), defaultdict(int)
    for c in commits:
        c["touched"] = set()
        human = c["kind"] == "h"  # авторство, и первое, и по правкам, получает только человек
        for ch in c["changes"]:
            st = ch[0][0]
            if st == "R":
                old, new = ch[1], ch[2]
                if new not in alive:
                    continue
                path = alive.pop(new)
                alive[old] = path
            elif st in "AM":
                if ch[1] not in alive:
                    continue
                path = alive[ch[1]]
                if st == "A":
                    if human:
                        first[path] = c["dev"]
                    alive.pop(ch[1])
            else:
                continue
            total[path] += 1
            c["touched"].add(path)
            if human:
                deliveries[path][c["dev"]] += 1
    return first, deliveries, total


def authorship(files, first, deliveries, total):
    """Автор файла: нормированный DOA выше 0,75 и абсолютный не ниже 3,293."""
    authors = defaultdict(set)
    for path in files:
        doa = {}
        for dev, dl in deliveries[path].items():
            fa = 1 if first.get(path) == dev else 0
            ac = total[path] - dl
            doa[dev] = 3.293 + 1.098 * fa + 0.164 * dl - 0.321 * math.log(1 + ac)
        if not doa:
            continue
        top = max(doa.values())
        for dev, v in doa.items():
            if v / top > DOA_SHARE and v >= DOA_MIN:
                authors[dev].add(path)
    return authors


def biggest(authors):
    """Автор с наибольшим числом файлов; при равенстве — первый по номеру."""
    return max(sorted(authors), key=lambda k: len(authors[k]))


def covered(authors):
    return set().union(*authors.values())


def truck_factor(authors, n_files):
    """Жадный алгоритм: убираем самого крупного автора, пока покрытие не меньше 50%."""
    left = dict(authors)
    tf = 0
    while left:
        if len(covered(left)) / n_files < COVERAGE:
            break
        left.pop(biggest(left))
        tf += 1
    return tf


def orphan_share(files, authors):
    owned = covered(authors)
    return 100.0 * sum(1 for f in files if f not in owned) / len(files)


def analyze(path):
    name, head, files, commits = load(path)
    first, deliveries, total = trace(files, commits)
    authors = authorship(files, first, deliveries, total)

    last = {}
    for c in commits:
        if c["kind"] == "h":
            last[c["dev"]] = max(last.get(c["dev"], ""), c["date"])

    def since(days):
        return (date.fromisoformat(head) - timedelta(days=days)).isoformat()

    def active_since(days, pool=authors):
        cut = since(days)
        return {k: v for k, v in pool.items() if last.get(k, "") >= cut}

    def metrics(pool):
        """Truck factor и доля ничьих файлов: сейчас и если уйдёт крупнейший активный."""
        active = active_since(ACTIVE_DAYS, pool)
        leader = biggest(active) if active else None
        return dict(
            tf_all=truck_factor(pool, len(files)),
            tf_active=truck_factor(active, len(files)),
            orphan_now=orphan_share(files, active),
            orphan_leader=orphan_share(files, {k: v for k, v in active.items() if k != leader}),
        )

    window = {days: orphan_share(files, active_since(days)) for days in WINDOWS}

    cut = since(ACTIVE_DAYS)
    year = [c for c in commits if c["date"] >= cut]
    agent = [c for c in year if c["agent_co"] or c["kind"] == "a"]
    agent_files = set().union(*(c["touched"] for c in agent))
    # файлы, где коммит с агентом записан на человека, а git считает этого человека автором
    credited = {p for c in agent if c["kind"] == "h"
                for p in c["touched"] if p in authors.get(c["dev"], ())}

    # Проверка чувствительности: правка с агентом не добавляет авторства человеку,
    # но остаётся чужой правкой файла. Активность людей берётся прежняя.
    no_agent = [dict(c, kind="a") if c["agent_co"] else c for c in commits]
    authors_na = authorship(files, *trace(files, no_agent))

    return dict(
        name=name, head=head, files=len(files), commits=len(commits),
        devs=len({c["dev"] for c in commits if c["kind"] == "h"}),
        **metrics(authors),
        year_commits=len(year), agent_commits=len(agent),
        agent_files=len(agent_files), agent_credited=len(credited),
        window=window, na=metrics(authors_na),
    )


TF_KEYS = ("tf_all", "tf_active", "orphan_now", "orphan_leader")
TF_FMT = "%6d  %8d  %11.1f%%  %15.1f%%"


def main(paths):
    rows = [analyze(p) for p in sorted(paths)]
    print("Проект               HEAD        Файлов  Коммитов  Людей  TF всё  TF актив  Ничьё сейчас  Ничьё без лидера")
    for r in rows:
        print("%-20s %-10s  %6d  %8d  %5d  " % (r["name"], r["head"], r["files"], r["commits"], r["devs"])
              + TF_FMT % tuple(r[k] for k in TF_KEYS))
    print()
    print("Проект               Коммитов за год  С агентом  Файлов с агентом  Из них автор по git тот, кто коммитил")
    for r in rows:
        print("%-20s %15d  %9d  %16d  %d" % (
            r["name"], r["year_commits"], r["agent_commits"], r["agent_files"], r["agent_credited"]))
    print()
    print("Проект               Ничьё при окне активности: 6 мес.  12 мес.  24 мес.")
    for r in rows:
        w = r["window"]
        print("%-20s %33.1f%%  %6.1f%%  %6.1f%%" % (r["name"], w[180], w[365], w[730]))
    print()
    print("Агент без авторства   TF всё  TF актив  Ничьё сейчас  Ничьё без лидера")
    for r in rows:
        print("%-20s " % r["name"] + TF_FMT % tuple(r["na"][k] for k in TF_KEYS))


if __name__ == "__main__":
    main(sys.argv[1:])
