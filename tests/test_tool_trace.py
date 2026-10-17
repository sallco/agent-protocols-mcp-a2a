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
