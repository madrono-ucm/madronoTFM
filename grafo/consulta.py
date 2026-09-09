"""Consulta de solo lectura contra el grafo urbano real en Neo4j (FIL_67).

Un ayudante de línea de comandos para inspeccionar la instancia AuraDB sin
abrir la consola web: resuelve credenciales, abre una sesión **de solo
lectura** y imprime las filas.

    python -m grafo.consulta "MATCH (e:EstacionMedida) RETURN e.tipo, count(*) AS n ORDER BY n DESC"
    python -m grafo.consulta --json "MATCH (l:Lugar {tipo:'recinto'}) RETURN l.nombre LIMIT 5"

Credenciales, por orden:
1. Variables de entorno `NEO4J_URI` / `NEO4J_USERNAME` / `NEO4J_PASSWORD`
   (`NEO4J_DATABASE` opcional; sin definir se usa la home database).
2. SSM `/madrono-tfm/dev/secrets/neo4j-{uri,username,password,database}`
   (`--with-decryption`), si `boto3` está disponible y hay credenciales AWS
   (`AWS_PROFILE=madrono`). Ver `infra/OPERACION.md`.

Rechaza cualquier sentencia con cláusulas de escritura antes de enviarla
(la sesión ya es `READ`, esto es una segunda red). Uso previsto: dev /
depuración, no una vía de cara al usuario -- para eso, ver FIL_67 Parte 2B.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

_ESCRITURA = re.compile(
    r"\b(CREATE|MERGE|DELETE|DETACH|SET|REMOVE|DROP|FOREACH|LOAD\s+CSV)\b"
    r"|CALL\s+(?:apoc|gds)\.[\w.]*\.(?:create|write|delete|set|remove|drop)",
    re.IGNORECASE,
)

_SSM_KEYS = ("uri", "username", "password", "database")


def _creds_desde_ssm() -> "dict[str, str] | None":
    try:
        import boto3
    except ImportError:
        return None
    try:
        ssm = boto3.client("ssm", region_name=os.environ.get("AWS_DEFAULT_REGION", "eu-west-1"))
        got = ssm.get_parameters(
            Names=[f"/madrono-tfm/dev/secrets/neo4j-{k}" for k in _SSM_KEYS],
            WithDecryption=True,
        )["Parameters"]
    except Exception:  # noqa: BLE001 - sin AWS/permisos: se cae a las env vars
        return None
    return {p["Name"].rsplit("-", 1)[-1]: p["Value"] for p in got}


def _resolver_credenciales() -> "tuple[str, str, str, str | None]":
    if os.environ.get("NEO4J_URI") and os.environ.get("NEO4J_PASSWORD"):
        return (
            os.environ["NEO4J_URI"],
            os.environ.get("NEO4J_USERNAME", "neo4j"),
            os.environ["NEO4J_PASSWORD"],
            os.environ.get("NEO4J_DATABASE") or None,
        )
    creds = _creds_desde_ssm()
    if not creds:
        raise SystemExit(
            "sin credenciales: define NEO4J_URI/NEO4J_USERNAME/NEO4J_PASSWORD "
            "o deja que boto3 lea SSM (AWS_PROFILE=madrono)."
        )
    return creds["uri"], creds["username"], creds["password"], creds.get("database") or None


def ejecutar(cypher: str, *, limite: int = 200) -> "list[dict]":
    """Corre `cypher` en una sesión de solo lectura y devuelve hasta
    `limite` filas como `dict`. Lanza `ValueError` si la sentencia parece de
    escritura."""
    if _ESCRITURA.search(cypher):
        raise ValueError("la sentencia contiene cláusulas de escritura; este módulo es solo lectura")

    from neo4j import GraphDatabase

    uri, user, password, database = _resolver_credenciales()
    driver = GraphDatabase.driver(uri, auth=(user, password))
    try:
        with driver.session(database=database, default_access_mode="READ") as session:
            result = session.run(cypher)
            filas = []
            for i, record in enumerate(result):
                if i >= limite:
                    break
                filas.append(dict(record))
            return filas
    finally:
        driver.close()


def _imprimir_tabla(filas: "list[dict]") -> None:
    if not filas:
        print("(0 filas)")
        return
    columnas = list(filas[0].keys())
    anchos = {c: max(len(c), *(len(str(f.get(c, ""))) for f in filas)) for c in columnas}
    print("  ".join(c.ljust(anchos[c]) for c in columnas))
    print("  ".join("-" * anchos[c] for c in columnas))
    for f in filas:
        print("  ".join(str(f.get(c, "")).ljust(anchos[c]) for c in columnas))
    print(f"\n({len(filas)} filas)")


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(description="Consulta de solo lectura contra el grafo Neo4j (FIL_67).")
    parser.add_argument("cypher", help="sentencia Cypher de lectura")
    parser.add_argument("--json", action="store_true", help="salida como JSON en vez de tabla")
    parser.add_argument("--limite", type=int, default=200, help="máximo de filas a traer (por defecto 200)")
    args = parser.parse_args(argv)

    try:
        filas = ejecutar(args.cypher, limite=args.limite)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(filas, ensure_ascii=False, indent=2, default=str))
    else:
        _imprimir_tabla(filas)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
