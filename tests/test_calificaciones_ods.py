"""Pruebas del lector de exportaciones ODS de calificaciones."""

from pathlib import Path
from zipfile import ZipFile

import pytest

from gesaula.actions.calificaciones_ods import (
    AlumnoCalificaciones,
    ColumnaCalificacion,
    ErrorArchivoCalificaciones,
    ErrorPreparacionCalificaciones,
    InformeCalificaciones,
    SeleccionCalificaciones,
    leer_calificaciones_ods,
    normalizar_nombre,
    preparar_plan_calificaciones,
)
from gesaula.moodle.models import AlumnoLevelUp


def _crear_ods(ruta: Path, contenido_tabla: str) -> None:
    contenido = f"""<?xml version="1.0" encoding="UTF-8"?>
    <office:document-content
      xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"
      xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0"
      xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0">
      <office:body><office:spreadsheet>
        <table:table table:name="Calificaciones">
          {contenido_tabla}
        </table:table>
      </office:spreadsheet></office:body>
    </office:document-content>
    """
    with ZipFile(ruta, "w") as archivo:
        archivo.writestr("content.xml", contenido)


def _celda(texto: str, *, tipo: str = "string", valor: str | None = None) -> str:
    atributo_valor = f' office:value="{valor}"' if valor is not None else ""
    return (
        f'<table:table-cell office:value-type="{tipo}"{atributo_valor}>'
        f"<text:p>{texto}</text:p></table:table-cell>"
    )


def test_lee_alumnos_y_solo_columnas_de_calificacion(tmp_path: Path) -> None:
    ruta = tmp_path / "calificaciones.ods"
    cabeceras = "".join(
        _celda(texto)
        for texto in (
            "Nombre",
            "Apellido(s)",
            "Dirección de correo",
            "Cuestionario 1 (Real)",
            "Total UT1 (Real)",
            "Última descarga de este curso",
        )
    )
    alumno = "".join(
        (
            _celda("Ana"),
            _celda("Ejemplo García"),
            _celda("ana@example.test"),
            _celda("7,50", tipo="float", valor="7.5"),
            _celda("-"),
            _celda("jueves"),
        )
    )
    _crear_ods(
        ruta,
        f"<table:table-row>{cabeceras}</table:table-row>"
        f"<table:table-row>{alumno}</table:table-row>",
    )

    informe = leer_calificaciones_ods(ruta)

    assert informe.hoja == "Calificaciones"
    assert [columna.nombre for columna in informe.columnas] == [
        "Cuestionario 1 (Real)",
        "Total UT1 (Real)",
    ]
    assert len(informe.alumnos) == 1
    assert informe.alumnos[0].nombre_completo == "Ana Ejemplo García"
    assert informe.alumnos[0].calificaciones == (7.5, None)


def test_rechaza_hoja_sin_apellidos(tmp_path: Path) -> None:
    ruta = tmp_path / "incompleto.ods"
    _crear_ods(
        ruta,
        "<table:table-row>"
        f"{_celda('Nombre')}{_celda('Cuestionario')}"
        "</table:table-row>",
    )

    with pytest.raises(ErrorArchivoCalificaciones, match="apellido"):
        leer_calificaciones_ods(ruta)


def test_normaliza_nombres_sin_hacer_coincidencias_aproximadas() -> None:
    assert normalizar_nombre("  María-José  Muñoz ") == "maria jose munoz"


def test_calcula_y_suma_cada_columna_redondeada_hacia_arriba() -> None:
    columnas = (
        ColumnaCalificacion(3, "Control"),
        ColumnaCalificacion(4, "Examen"),
    )
    informe = InformeCalificaciones(
        hoja="Calificaciones",
        columnas=columnas,
        alumnos=(
            AlumnoCalificaciones(
                nombre="María José",
                apellidos="Muñoz-Pérez",
                correo="",
                calificaciones=(7.21, 6.31),
            ),
        ),
    )
    seleccion = SeleccionCalificaciones(
        columnas=columnas,
        multiplicador=10,
    )
    alumnos_moodle = (
        AlumnoLevelUp(
            id=42,
            nombre="MARIA JOSE MUÑOZ PÉREZ",
            nivel=1,
            px=100,
            context_id=85744,
        ),
    )

    plan = preparar_plan_calificaciones(
        informe,
        seleccion,
        alumnos_moodle,
    )

    (incremento,) = plan.incrementos
    assert incremento.incremento == 137
    assert incremento.nuevo_total == 237
    assert plan.alumnos_sin_calificacion == 0


def test_no_prepara_escrituras_con_nombres_ambiguos() -> None:
    columna = ColumnaCalificacion(3, "Control")
    informe = InformeCalificaciones(
        hoja="Calificaciones",
        columnas=(columna,),
        alumnos=(
            AlumnoCalificaciones("Ana", "Ejemplo", "", (5.0,)),
            AlumnoCalificaciones("Ana", "Ejemplo", "", (8.0,)),
        ),
    )

    with pytest.raises(ErrorPreparacionCalificaciones, match="ambiguo"):
        preparar_plan_calificaciones(
            informe,
            SeleccionCalificaciones((columna,), 10),
            (AlumnoLevelUp(42, "Ana Ejemplo", 1, 0, 85744),),
        )
