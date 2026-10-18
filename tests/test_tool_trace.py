from contextvars import Context

from core.tools import (
    instrumentar_herramienta,
    iniciar_traza_herramientas,
    obtener_traza_herramientas,
)


def test_traza_registra_nombre_argumentos_y_resultado() -> None:
    @instrumentar_herramienta("herramienta_prueba")
    def herramienta(valor: int) -> dict[str, int]:
        return {"valor": valor}

    iniciar_traza_herramientas()
    assert herramienta(7) == {"valor": 7}

    traza = obtener_traza_herramientas()
    assert len(traza) == 1
    assert traza[0]["nombre"] == "herramienta_prueba"
    assert traza[0]["argumentos"] == {"0": "7"}
    assert traza[0]["resultado"] == {"valor": 7}
    assert traza[0]["exitosa"] is True


def test_traza_registra_error_y_no_oculta_la_excepcion() -> None:
    @instrumentar_herramienta("herramienta_fallida")
    def herramienta_fallida() -> None:
        raise RuntimeError("fallo controlado")

    iniciar_traza_herramientas()
    try:
        herramienta_fallida()
    except RuntimeError as error:
        assert str(error) == "fallo controlado"
    else:
        raise AssertionError("La herramienta debía propagar el error")

    traza = obtener_traza_herramientas()
    assert traza[0]["nombre"] == "herramienta_fallida"
    assert traza[0]["exitosa"] is False
    assert traza[0]["error"] == "fallo controlado"


def test_ejecuciones_sin_traza_activa_no_acumulan_resultados() -> None:
    @instrumentar_herramienta("sin_traza")
    def herramienta():
        return "resultado"

    contexto = Context()
    assert contexto.run(herramienta) == "resultado"
    assert contexto.run(obtener_traza_herramientas) == []


def test_trazas_de_contextos_distintos_no_se_mezclan() -> None:
    @instrumentar_herramienta("aislada")
    def herramienta(valor):
        return valor

    primero, segundo = Context(), Context()
    primero.run(iniciar_traza_herramientas)
    primero.run(herramienta, "primero")
    segundo.run(iniciar_traza_herramientas)
    segundo.run(herramienta, "segundo")

    assert primero.run(obtener_traza_herramientas)[0]["resultado"] == "primero"
    assert segundo.run(obtener_traza_herramientas)[0]["resultado"] == "segundo"
