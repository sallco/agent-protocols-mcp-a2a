-- Migración 002: Tabla de citas con control de franjas horarias y evidencia de seguridad
CREATE TABLE IF NOT EXISTS citas (
    id UUID PRIMARY KEY,
    idempotency_key TEXT UNIQUE NOT NULL,
    nombre TEXT NOT NULL,
    fecha DATE NOT NULL,
    hora TEXT NOT NULL,
    veredicto TEXT NOT NULL,
    advertencias JSONB NOT NULL DEFAULT '[]'::jsonb,
    evidencia_clima JSONB NOT NULL,
    evaluacion_seguridad JSONB NOT NULL,
    arquitectura TEXT NOT NULL,
    creado_en TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT citas_franja_unica UNIQUE (fecha, hora),
    CONSTRAINT citas_nombre_no_vacio CHECK (btrim(nombre) <> ''),
    CONSTRAINT citas_hora_valida CHECK (hora IN ('08:00', '09:00', '10:00', '11:00', '12:00', '13:00', '14:00', '15:00')),
    CONSTRAINT citas_veredicto_valido CHECK (veredicto IN ('IDEAL', 'MARGINAL'))
);

CREATE INDEX IF NOT EXISTS citas_fecha_idx ON citas (fecha);
