"""Esquema de la respuesta del asistente (memoria del TFM, apartado 6.7).

La memoria describe el asistente respondiendo preguntas del tipo «¿voy al
centro a las nueve de la noche del viernes?» con tres elementos: un
veredicto, un nivel de fiabilidad y una explicación trazable a los datos que
la sustentan. `RespuestaAsistente` es ese contrato, como modelo Pydantic
reutilizable por cualquier router/tool que lo necesite en el futuro — hoy no
lo construye nadie todavía (no hay lógica real, ver
`asistente/mcp_agent/tools.py`), pero el esquema en sí no depende de que
exista esa lógica.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

from asistente.timeutils import now_madrid


class Veredicto(str, Enum):
    """Resultado de alto nivel de la pregunta planteada al asistente."""

    FAVORABLE = "favorable"
    DESFAVORABLE = "desfavorable"
    CON_PRECAUCION = "con_precaucion"


class NivelFiabilidad(str, Enum):
    """Cuánto se puede confiar en el veredicto, dados los datos disponibles.

    No es una medida de la calidad del dato en sí (eso ya lo filtra la
    puerta de calidad de `procesamiento/`, ver doc/041), sino de cuánto
    cubren los datos disponibles la pregunta concreta: por ejemplo, una
    previsión a varios días vista con pocas fuentes coincidentes debería
    resultar en `BAJA`, aunque cada dato individual sea válido.
    """

    ALTA = "alta"
    MEDIA = "media"
    BAJA = "baja"


class FuenteConsultada(BaseModel):
    """Un dato concreto citado en la explicación, trazable a su origen."""

    dataset: str
    resumen: str
    consultado_en: datetime | None = None


class RespuestaAsistente(BaseModel):
    """Respuesta completa del asistente a una pregunta en lenguaje natural."""

    pregunta: str
    veredicto: Veredicto
    fiabilidad: NivelFiabilidad
    explicacion: str
    fuentes: list[FuenteConsultada] = Field(default_factory=list)
    generado_en: datetime = Field(default_factory=now_madrid)


class RespuestaPrevision(BaseModel):
    """Envoltorio común de las tools de previsión (`*_prevista`, `FIL_15`).

    Toda tool que sirva una cifra desde un modelo ONNX de `ML_07`
    (`calidad_aire_prevista` de `ML_09`, `trafico_prevista` de `FIL_13`, y
    cualquier `afluencia_prevista` futura) devuelve una **subclase** de esta:
    mismos campos de procedencia y de degradación, más los específicos del
    dominio (estación/contaminante para calidad del aire, punto/lugar para
    tráfico).

    Contrato de degradación (ninguna ruta lanza excepción hacia el cliente
    MCP): si falta el `.onnx`, si Gold no tiene lags suficientes para
    `momento`, o si Neo4j/Athena fallan, se devuelve el objeto con
    `disponible=False`, `valor_previsto=None`, `nivel_previsto="sin_datos"` y
    un `motivo` legible. `disponible=True` ⇔ `valor_previsto is not None`.

    Campos de la petición
    ---------------------
    `horizonte_horas`  Horas por delante previstas (1, 3 o 6).
    `momento`          Instante de **anclaje**: última hora con lectura real
                       en Gold (Gold va con retraso, así que el forecast se
                       ancla al último dato real, igual que el feature store
                       de `ML_01`).
    `momento_objetivo` Hora de pared a la que aplica la previsión
                       (`momento + horizonte_horas`). `None` si no hubo
                       anclaje (sin datos).

    Resultado
    ---------
    `disponible`       ¿Se pudo producir una cifra?
    `valor_previsto`   Valor del target a `horizonte_horas` (µg/m³ /
                       `avg_service_level` / …). `None` si `not disponible`.
    `valor_actual`     Última lectura real, para contexto.
    `unidad`           Unidad de `valor_previsto`/`valor_actual`.
    `nivel_previsto`   Etiqueta simplificada del dominio
                       (`"buena"`… / `"fluido"`… / `"sin_datos"`).
    `motivo`           Por qué no hay cifra (solo si `not disponible`).

    Procedencia / confianza
    -----------------------
    `modelo`            `<target>_h<H>.onnx` + nombre del modelo del registry
                        (`version_modelo` de la tarea).
    `data_completeness` Fracción de {actual, lag 1/2/3/24 h} presente (0..1);
                        proxy de confianza — baja cuando faltan features.
    `ventana_datos`     Rango de fechas de los lags usados (`"YYYY-MM-DD..YYYY-MM-DD"`).
    `fuente_dataset`    Tabla Gold de origen.
    `generado_en`       Momento en que se construyó **esta respuesta** (≠ `momento`).
    """

    # --- petición ---
    horizonte_horas: int
    momento: datetime
    momento_objetivo: datetime | None = None

    # --- resultado ---
    disponible: bool = False
    valor_previsto: float | None = None
    valor_actual: float | None = None
    unidad: str | None = None
    nivel_previsto: str = "sin_datos"
    motivo: str | None = None

    # --- procedencia / confianza ---
    modelo: str | None = None
    data_completeness: float = 0.0
    ventana_datos: str | None = None
    fuente_dataset: str
    generado_en: datetime = Field(default_factory=now_madrid)
