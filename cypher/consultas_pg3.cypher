// SITA · PG3 · Grupo 19 — Lista blanca de consultas del asistente (solo lectura).
// Parámetros: $legajo (texto), $codigo, $codigos, $alcance, $filtro, $horizonte_meses, $horas_hipoteticas.
// Generado con: python -m sita --exportar

// ================================================================================================
// CAT_ESTUDIANTES
// ================================================================================================
MATCH (e:Estudiante) RETURN toString(e.legajo) AS legajo, e.nombre AS nombre ORDER BY nombre
;

// ================================================================================================
// CAT_ASIGNATURAS
// ================================================================================================
MATCH (a:Asignatura) WHERE a.codigo IS NOT NULL RETURN a.codigo AS codigo, a.sigla AS sigla, a.nombre AS nombre ORDER BY codigo
;

// ================================================================================================
// X_CONTEXTO
// ================================================================================================
MATCH (q:Consulta)-[:SOLICITADA_POR]->(e:Estudiante)
WHERE toString(e.legajo) = $legajo
RETURN {
  estudiante: e.nombre, legajo: toString(e.legajo),
  consulta: q.id, estado: q.estado, corte_en: q.corte_en,
  periodo: [(q)-[:REFERIDA_A]->(p:Periodo) | p.id][0],
  confiabilidad: [(q)-[:PRODUCE]->(cf:ConfiabilidadDato) | {etiqueta: cf.etiqueta, valor: round(cf.valor, 3)}][0],
  reserva: [(q)-[:PRODUCE]->(rv:Advertencia) WHERE rv.tipo = 'juicio_con_reserva' | rv.mensaje][0]
} AS contexto
LIMIT 1
;

// ================================================================================================
// X_CORTE
// ================================================================================================
MATCH (e:Estudiante {legajo: $legajo})<-[:SOLICITADA_POR]-(q:Consulta)
WITH e, q, [(q)-[:PRODUCE]->(s:SolicitudDatos) | s]
           + [(e)-[:POSEE]->(:HistoriaAcademica)-[:ORIGINA]->(s:SolicitudDatos) | s] AS solicitudes
WHERE size(solicitudes) > 0
WITH e, q, solicitudes[0] AS s
RETURN {estudiante: e.nombre, estado_consulta: q.estado, corte_en: q.corte_en, ambito: s.ambito, motivo: s.motivo,
        faltantes: s.faltantes,
        reglas: [(s)-[:JUSTIFICADO_POR]->(r:Regla) | {id: r.id, enunciado: r.enunciado, estado: r.estado}],
        confiabilidad_del_dato_M1: [(q)-[:PRODUCE]->(cf:ConfiabilidadDato) | {etiqueta: cf.etiqueta, valor: round(cf.valor, 2)}][0],
        dictamenes_conservados: COUNT { (q)-[:PRODUCE]->(:Dictamen) }} AS traza_corte
;

// ================================================================================================
// M1_DICTAMEN
// ================================================================================================
MATCH (q:Consulta)-[:SOLICITADA_POR]->(e:Estudiante)
WHERE toString(e.legajo) = $legajo
MATCH (a:Asignatura {codigo: $codigo})
OPTIONAL MATCH (q)-[:PRODUCE]->(d:Dictamen {alcance: $alcance})-[:SOBRE]->(a)
WITH q, e, a, d,
     [(e)-[:POSEE]->(:HistoriaAcademica)-[:REGISTRA]->(s:EstadoAcademico)-[:REFIERE_A]->(a) | s.valor] AS est
RETURN {
  estudiante: e.nombre, legajo: toString(e.legajo),
  asignatura: {codigo: a.codigo, nombre: a.nombre,
               estado_en_historia: coalesce(est[0], 'pendiente (sin registro)')},
  alcance_consultado: $alcance,
  dictamen: CASE WHEN d IS NULL THEN null ELSE {
    id: d.id,
    tipo: CASE WHEN d:BloqueoHeredado THEN 'BloqueoHeredado' WHEN d:Bloqueo THEN 'BloqueoDirecto'
               WHEN d:HabilitacionRendir THEN 'HabilitacionRendir' ELSE 'HabilitacionCursar' END,
    condicionado: d.condicionado,
    profundidad: d.profundidad,
    causas: [(d)-[o:ORIGINADO_POR]->(c:Correlatividad)-[:APUNTA_A]->(y:Asignatura) |
             {correlatividad: c.id, tipo: c.tipo, asignatura: y.nombre,
              estado_encontrado: o.estado_encontrado, condicionada: o.condicionado, causa: o.causa}],
    condiciones_verificadas: [(d)-[:VERIFICA]->(c:Correlatividad)-[:APUNTA_A]->(y:Asignatura) |
             {correlatividad: c.id, tipo: c.tipo, asignatura: y.nombre}],
    hereda_de: [(d)-[:HEREDA_DE]->(p:Dictamen)-[:SOBRE]->(pa:Asignatura) |
             {asignatura: pa.nombre, dictamen: p.id}],
    causa_raiz: [(d)-[:CAUSA_RAIZ]->(c:Correlatividad)-[:APUNTA_A]->(y:Asignatura) |
             {correlatividad: c.id, tipo: c.tipo, asignatura: y.nombre}],
    reglas: [(d)-[:JUSTIFICADO_POR]->(r:Regla) |
             {id: r.id, enunciado: r.enunciado, estado: r.estado}]
  } END,
  correlativas_de_la_asignatura: [(a)-[:EXIGE]->(c:Correlatividad)-[:APUNTA_A]->(y:Asignatura) |
    {tipo: c.tipo, asignatura: y.nombre,
     estado_estudiante: coalesce(
       [(e)-[:POSEE]->(:HistoriaAcademica)-[:REGISTRA]->(s2:EstadoAcademico)-[:REFIERE_A]->(y) | s2.valor][0],
       'pendiente (sin registro)')}],
  advertencias: [(q)-[:PRODUCE]->(w:Advertencia)-[:SOBRE]->(a) |
    {tipo: w.tipo, mensaje: w.mensaje,
     reglas: [(w)-[:JUSTIFICADO_POR]->(r:Regla) | {id: r.id, enunciado: r.enunciado, estado: r.estado}]}],

  contexto_m1: {
    consulta: q.id, estado_consulta: q.estado, corte_en: q.corte_en,
    confiabilidad: [(q)-[:PRODUCE]->(cf:ConfiabilidadDato) |
                    {etiqueta: cf.etiqueta, valor: round(cf.valor, 3)}][0],
    reserva: size([(q)-[:PRODUCE]->(rv:Advertencia) WHERE rv.tipo = 'juicio_con_reserva' | rv]) > 0
  }
} AS resultado
;

// ================================================================================================
// M1_HABILITACIONES
// ================================================================================================
MATCH (q:Consulta)-[:SOLICITADA_POR]->(e:Estudiante)
WHERE toString(e.legajo) = $legajo
OPTIONAL MATCH (q)-[:PRODUCE]->(d:Dictamen {alcance: 'cursar'})-[:SOBRE]->(a:Asignatura)
WITH q, e, d, a ORDER BY a.codigo
WITH q, e, [x IN collect(CASE WHEN d IS NULL THEN null ELSE {
    asignatura: a.nombre, codigo: a.codigo,
    dictamen: CASE WHEN d:Bloqueo THEN 'bloqueada' ELSE 'habilitada' END,
    heredado: d:BloqueoHeredado,
    condicionado: coalesce(d.condicionado, false),
    causas: [(d)-[o:ORIGINADO_POR]->(:Correlatividad) | o.causa],
    sin_oferta: coalesce(d.sin_oferta, false)
                OR size([(q)-[:PRODUCE]->(w:Advertencia)-[:SOBRE]->(a) WHERE w.tipo = 'sin_oferta' | w]) > 0,
    reglas: [(d)-[:JUSTIFICADO_POR]->(r:Regla) | r.id]
  } END) WHERE $filtro = 'todas'
            OR ($filtro = 'habilitadas' AND x.dictamen = 'habilitada')
            OR ($filtro = 'bloqueadas' AND x.dictamen = 'bloqueada')] AS dictamenes
RETURN {
  estudiante: e.nombre, legajo: toString(e.legajo), filtro: $filtro,
  periodo: [(q)-[:REFERIDA_A]->(p:Periodo) | p.id][0],
  total_habilitadas: size([x IN dictamenes WHERE x.dictamen = 'habilitada']),
  total_bloqueadas: size([x IN dictamenes WHERE x.dictamen = 'bloqueada']),
  dictamenes: dictamenes,
  glosario_reglas: [r IN reduce(acc = [], x IN [(q)-[:PRODUCE]->(:Dictamen)-[:JUSTIFICADO_POR]->(r0:Regla) | r0] |
                     CASE WHEN x IN acc THEN acc ELSE acc + x END) |
                   {id: r.id, enunciado: r.enunciado, estado: r.estado}],

  contexto_m1: {
    consulta: q.id, estado_consulta: q.estado, corte_en: q.corte_en,
    confiabilidad: [(q)-[:PRODUCE]->(cf:ConfiabilidadDato) |
                    {etiqueta: cf.etiqueta, valor: round(cf.valor, 3)}][0],
    reserva: size([(q)-[:PRODUCE]->(rv:Advertencia) WHERE rv.tipo = 'juicio_con_reserva' | rv]) > 0
  }
} AS resultado
;

// ================================================================================================
// M1_REGULARIDADES
// ================================================================================================
MATCH (q:Consulta)-[:SOLICITADA_POR]->(e:Estudiante)
WHERE toString(e.legajo) = $legajo
OPTIONAL MATCH (e)-[:POSEE]->(:HistoriaAcademica)-[:REGISTRA]->(s:EstadoAcademico)-[:REFIERE_A]->(a:Asignatura),
               (s)-[:SUSTENTADO_POR]->(g:Regularidad)
WITH q, e, collect(CASE WHEN g IS NULL OR ($codigo IS NOT NULL AND a.codigo <> $codigo) THEN null ELSE {
    asignatura: a.nombre, codigo: a.codigo, estado_actual: s.valor,
    fecha_obtencion: toString(g.fecha_obtencion),
    fecha_vencimiento: toString(g.fecha_vencimiento),
    vigente: g.vigente, meses_para_vencer: round(g.meses_para_vencer, 1),
    final_rendido: g.final_rendido,
    vencimiento_registrado: size([(v:VencimientoRegularidad)-[:INVALIDA]->(g) | v]) > 0
  } END) AS regularidades
OPTIONAL MATCH (h01:Regla {id: 'H-01'})
RETURN {
  estudiante: e.nombre, legajo: toString(e.legajo),
  asignatura_consultada: $codigo,
  inicio_periodo: [(q)-[:REFERIDA_A]->(p:Periodo) | toString(p.fecha_inicio)][0],
  regularidades: regularidades,
  regla: {id: h01.id, enunciado: h01.enunciado, estado: h01.estado},

  contexto_m1: {
    consulta: q.id, estado_consulta: q.estado, corte_en: q.corte_en,
    confiabilidad: [(q)-[:PRODUCE]->(cf:ConfiabilidadDato) |
                    {etiqueta: cf.etiqueta, valor: round(cf.valor, 3)}][0],
    reserva: size([(q)-[:PRODUCE]->(rv:Advertencia) WHERE rv.tipo = 'juicio_con_reserva' | rv]) > 0
  }
} AS resultado
;

// ================================================================================================
// M1_HISTORIA
// ================================================================================================
MATCH (q:Consulta)-[:SOLICITADA_POR]->(e:Estudiante)
WHERE toString(e.legajo) = $legajo
OPTIONAL MATCH (e)-[:POSEE]->(h:HistoriaAcademica)
OPTIONAL MATCH (q)-[:PRODUCE]->(cf:ConfiabilidadDato)
OPTIONAL MATCH (x01:Regla {id: 'X-01'})
RETURN {
  estudiante: e.nombre, legajo: toString(e.legajo),
  historia: {fecha_actualizacion: toString(h.fecha_actualizacion),
             inconsistencias: h.inconsistencias,
             antiguedad_meses: round(h.antiguedad_meses, 2),
             completitud: round(h.completitud, 3)},
  mediciones_m1: [(q)-[:MIDE]->(m:Medicion) WHERE m.contexto = 'M1' |
                  {variable: m.variable, valor: round(m.valor, 3), etiqueta: m.etiqueta}],
  confiabilidad: CASE WHEN cf IS NULL THEN null ELSE {
    etiqueta: cf.etiqueta, valor: round(cf.valor, 3),
    antecedentes_sin_dato: cf.antecedentes_sin_dato,
    reglas_activadas: [(cf)-[j:JUSTIFICADO_POR]->(r:Regla) |
                       {id: r.id, alfa: round(j.alfa, 3), enunciado: r.enunciado, estado: r.estado}]
  } END,
  advertencias_m1: [(q)-[:PRODUCE]->(w:Advertencia) WHERE w.tipo = 'juicio_con_reserva' |
                    {tipo: w.tipo, mensaje: w.mensaje}],
  solicitudes_de_datos: [(q)-[:PRODUCE]->(sd:SolicitudDatos) |
                         {ambito: sd.ambito, motivo: sd.motivo, faltantes: sd.faltantes}] +
                        [(h)-[:ORIGINA]->(sd:SolicitudDatos) WHERE NOT (q)-[:PRODUCE]->(sd) |
                         {ambito: sd.ambito, motivo: sd.motivo, faltantes: sd.faltantes}],
  regla_corte: {id: x01.id, enunciado: x01.enunciado, estado: x01.estado},

  contexto_m1: {
    consulta: q.id, estado_consulta: q.estado, corte_en: q.corte_en,
    confiabilidad: [(q)-[:PRODUCE]->(cf:ConfiabilidadDato) |
                    {etiqueta: cf.etiqueta, valor: round(cf.valor, 3)}][0],
    reserva: size([(q)-[:PRODUCE]->(rv:Advertencia) WHERE rv.tipo = 'juicio_con_reserva' | rv]) > 0
  }
} AS resultado
;

// ================================================================================================
// M1_RECORRIDO
// ================================================================================================
MATCH (q:Consulta)-[:SOLICITADA_POR]->(e:Estudiante)
WHERE toString(e.legajo) = $legajo
MATCH (q)-[:PRODUCE]->(d:Dictamen {alcance: $alcance})-[:SOBRE]->(a:Asignatura {codigo: $codigo})
RETURN {
  camino: '(Estudiante)<-[:SOLICITADA_POR]-(Consulta)-[:PRODUCE]->(Dictamen)-[:SOBRE]->(Asignatura)',
  consulta: q.id, dictamen: d.id, asignatura: a.nombre, alcance: d.alcance,
  clase: [l IN labels(d) WHERE l IN ['HabilitacionCursar', 'HabilitacionRendir', 'BloqueoDirecto',
                                     'BloqueoHeredado', 'Bloqueo']],
  originado_por: [(d)-[o:ORIGINADO_POR]->(c:Correlatividad)-[:APUNTA_A]->(req:Asignatura) |
    {relacion: '(Dictamen)-[:ORIGINADO_POR]->(Correlatividad)-[:APUNTA_A]->(Asignatura)',
     correlatividad: c.id, exige: c.tipo, requisito: req.nombre,
     estado_en_historia: coalesce([(e)-[:POSEE]->(:HistoriaAcademica)-[:REGISTRA]->(s:EstadoAcademico)
                                   -[:REFIERE_A]->(req) | s.valor][0], 'sin registro'),
     estado_evaluado: o.estado_encontrado, condicionada: o.condicionado, causa: o.causa}],
  verifica: [(d)-[:VERIFICA]->(c:Correlatividad)-[:APUNTA_A]->(req:Asignatura) |
    {relacion: '(Dictamen)-[:VERIFICA]->(Correlatividad)-[:APUNTA_A]->(Asignatura)',
     correlatividad: c.id, exige: c.tipo, requisito: req.nombre,
     estado_en_historia: coalesce([(e)-[:POSEE]->(:HistoriaAcademica)-[:REGISTRA]->(s:EstadoAcademico)
                                   -[:REFIERE_A]->(req) | s.valor][0], 'sin registro')}],
  hereda_de: [(d)-[:HEREDA_DE]->(p:Dictamen)-[:SOBRE]->(pa:Asignatura) |
    {relacion: '(Dictamen)-[:HEREDA_DE]->(Dictamen)-[:SOBRE]->(Asignatura)', dictamen: p.id, asignatura: pa.nombre}],
  causa_raiz: [(d)-[:CAUSA_RAIZ]->(c:Correlatividad)-[:APUNTA_A]->(req:Asignatura) |
    {relacion: '(Dictamen)-[:CAUSA_RAIZ]->(Correlatividad)-[:APUNTA_A]->(Asignatura)',
     correlatividad: c.id, exige: c.tipo, requisito: req.nombre}],
  reglas: [(d)-[:JUSTIFICADO_POR]->(r:Regla) |
    {relacion: '(Dictamen)-[:JUSTIFICADO_POR]->(Regla)', id: r.id, estado: r.estado, enunciado: r.enunciado}]
} AS recorrido
;

// ================================================================================================
// M2_CAPACIDAD
// ================================================================================================
MATCH (e:Estudiante {legajo: $legajo})<-[:SOLICITADA_POR]-(q:Consulta)
OPTIONAL MATCH (e)-[:DECLARA_CONTEXTO]->(ctx:ContextoEstudiante)
OPTIONAL MATCH (q)-[:PRODUCE]->(ev:EvaluacionCarga)
OPTIONAL MATCH (ev)-[:DETERMINA]->(ta:TamanioAdmisible)
OPTIONAL MATCH (q)-[:PRODUCE]->(rs:RiesgoSobrecarga)
RETURN {
  estudiante: e.nombre, legajo: e.legajo, estado_consulta: q.estado, corte_en: q.corte_en,
  periodo: [(q)-[:REFERIDA_A]->(p:Periodo) | p.id][0],
  horas_trabajo_semanales: ctx.horas_trabajo_semanales,
  carga_h: round(ev.carga_horas, 2), capacidad_h: ev.capacidad_horas, holgura_h: round(ev.holgura_horas, 2),
  carga_anuales_en_curso_h: ev.carga_anuales_en_curso, anuales_en_curso: ev.anuales_en_curso,
  parametros_capacidad: [(pm:ParametroModelo)
                         WHERE pm.id IN ['dedicacion_total_sostenible', 'factor_estudio', 'horas_preparacion_final'] |
                         {id: pm.id, valor: pm.valor, unidad: pm.unidad, estado: pm.estado, descripcion: pm.descripcion}],
  riesgo_sobrecarga: {etiqueta: rs.etiqueta, valor: round(rs.valor, 2),
                      reglas: [(rs)-[j:JUSTIFICADO_POR]->(r:ReglaDifusa) | {regla: r.id, alfa: round(j.alfa, 2)}],
                      sin_dato: rs.antecedentes_sin_dato},
  tamano_base: ta.base, tamano_admisible: ta.valor, tope_declarado: ta.tope_declarado,
  ajustes: [(aj:Ajuste)-[:REDUCE]->(ta) | {tipo: [l IN labels(aj) WHERE l STARTS WITH 'AjustePor'][0],
                                           unidades: aj.unidades, causa: aj.causa,
                                           reglas: [(aj)-[:JUSTIFICADO_POR]->(r:Regla) |
                                                    {id: r.id, enunciado: r.enunciado, estado: r.estado}]}],
  items_evaluados: [(ev)-[:EVALUA]->(:ConjuntoCandidato)-[:CONTIENE]->(i:ItemCandidato) |
                    {asignatura: i.asignatura, alcance: i.alcance, horas_semanales: round(i.horas_dedicacion, 2)}],
  advertencias_m2: [(q)-[:PRODUCE]->(a:Advertencia) WHERE a.tipo IN ['margen_estrecho', 'sobrecarga_concentracion', 'discrepancia_tope']
                    | {tipo: a.tipo, mensaje: a.mensaje, reglas: [(a)-[:JUSTIFICADO_POR]->(r) | r.id]}],
  glosario_reglas: COLLECT {
    MATCH (q)-[:PRODUCE]->(:Conclusion)-[:JUSTIFICADO_POR]->(r:Regla)
    WHERE r.id STARTS WITH 'C-' OR r.id STARTS WITH 'RS' OR r.id = 'X-02'
    RETURN DISTINCT {id: r.id, enunciado: r.enunciado, estado: r.estado} AS regla
    ORDER BY regla.id}
} AS traza_m2
;

// ================================================================================================
// M3_Q1_RIESGO
// ================================================================================================
MATCH (e:Estudiante {legajo: $legajo})<-[:SOLICITADA_POR]-(q:Consulta)-[:REFERIDA_A]->(per:Periodo)
WITH e, q, per ORDER BY q.fecha DESC LIMIT 1
OPTIONAL MATCH (q)-[:PRODUCE]->(rr:ResultadoRiesgo)
OPTIONAL MATCH (rr)-[:ESTIMA]->(rk:RiesgoAtraso)
OPTIONAL MATCH (q)-[:PRODUCE]->(sol:SolicitudDatos)
OPTIONAL MATCH (e)-[:POSEE]->(h:HistoriaAcademica)
OPTIONAL MATCH (h)-[:TIENE_CONFIABILIDAD]->(conf:ConfiabilidadDato)
MATCH (pl:ParametroModelo {id: 'corte_alfa_llave'}), (pu:ParametroModelo {id: 'corte_alfa_urgencia'})
RETURN {
  estudiante: e {.legajo, .nombre, .anio_ingreso},
  consulta: q.id, periodo: per.id, fecha_referencia: toString(per.fecha_inicio),
  estado_consulta: q.estado, corte_en: q.corte_en,
  solicitud_de_datos: CASE WHEN sol IS NULL THEN null ELSE {ambito: sol.ambito, motivo: sol.motivo, faltantes: sol.faltantes,
                      reglas: coalesce([(sol)-[:JUSTIFICADO_POR]->(r:Regla) | r.id], [])} END,
  confiabilidad_del_dato: CASE WHEN conf IS NULL THEN null ELSE {etiqueta: conf.etiqueta, valor: conf.valor} END,
  nivel_nominal: rr.nivel_nominal, nivel_alcanzado: rr.nivel_alcanzado,
  riesgo_atraso: CASE WHEN rk IS NULL THEN null ELSE {
    valor: rk.valor, etiqueta: rk.etiqueta, salvedad_E13: rk.salvedad, antecedentes_sin_dato: rk.antecedentes_sin_dato,
    grados: [(rk)-[a:ACTIVA]->(t:TerminoLinguistico) | {etiqueta: t.nombre, mu: a.grado}],
    sistema_difuso: head([(rk)-[:CALCULADA_CON]->(sd:SistemaDifuso) |
                          sd {.id, .metodo, .op_and, .op_or, .implicacion, .agregacion, .defuzzificacion}])} END,
  reglas_difusas: [(rk)-[j:JUSTIFICADO_POR]->(r:Regla) | {id: r.id, enunciado: r.enunciado, estado: r.estado, alfa: j.alfa,
                   consecuente: head([(r)-[:CONSECUENTE]->(t:TerminoLinguistico) | t.nombre])}],
  arrastres: [(rr)-[:IDENTIFICA]->(f:Arrastre)-[:AFECTA_A]->(a:Asignatura) | {asignatura: a.nombre, estado: f.estado_asignatura,
              descendientes: a.cant_descendientes, grado_llave: a.grado_llave, peso: f.peso,
              reglas: [(f)-[:JUSTIFICADO_POR]->(r:Regla) | r.id]}],
  urgencias: [(rr)-[:IDENTIFICA]->(f:UrgenciaVencimiento)-[:AFECTA_A]->(a:Asignatura) | {asignatura: a.nombre,
              meses_para_vencer: f.meses, grado_urgencia: f.grado, severidad: f.severidad, a_confirmar: f.a_confirmar,
              vencimiento: head([(rg:Regularidad)-[:GENERA]->(f) | toString(rg.fecha_vencimiento)]),
              reglas: [(f)-[:JUSTIFICADO_POR]->(r:Regla) | r.id]}],
  cuellos_de_botella: [(rr)-[:IDENTIFICA]->(f:CuelloDeBotella) | {asignatura: f.asignatura, nivel_comprometido: f.nivel,
                       proporcion: f.proporcion}],
  ruta_critica: head([(rr)-[:IDENTIFICA]->(rc:RutaCritica) | rc.asignaturas]),
  asignaturas_llave: [(rr)-[l:IDENTIFICA_LLAVE]->(a:Asignatura) | {asignatura: a.nombre, grado_llave: l.grado}],
  capacidad_disponible: head([(m:Medicion)-[:MODULA]->(rk) | {horas_semanales: m.valor, etiqueta: m.etiqueta,
                        mu_baja: head([(m)-[p:PERTENECE]->(t:TerminoLinguistico {nombre: 'baja'}) | p.mu])}]),
  corte_alfa_llave: pl.valor,
  reglas: coalesce([(rr)-[:JUSTIFICADO_POR]->(r:Regla) | r {.id, .enunciado, .estado}], [])
        + coalesce([(rr)-[:IDENTIFICA]->()-[:JUSTIFICADO_POR]->(r:Regla) | r {.id, .enunciado, .estado}], [])
        + coalesce([(rk)-[:JUSTIFICADO_POR]->(r:Regla) WHERE NOT r:ReglaDifusa | r {.id, .enunciado, .estado}], [])
        + coalesce([(sol)-[:JUSTIFICADO_POR]->(r:Regla) | r {.id, .enunciado, .estado}], [])
} AS resultado
;

// ================================================================================================
// M3_Q2_URGENCIAS
// ================================================================================================
MATCH (e:Estudiante {legajo: $legajo})<-[:SOLICITADA_POR]-(q:Consulta)-[:REFERIDA_A]->(per:Periodo)
WITH e, q, per ORDER BY q.fecha DESC LIMIT 1
OPTIONAL MATCH (q)-[:PRODUCE]->(rr:ResultadoRiesgo)
OPTIONAL MATCH (rr)-[:ESTIMA]->(rk:RiesgoAtraso)
OPTIONAL MATCH (q)-[:PRODUCE]->(sol:SolicitudDatos)
OPTIONAL MATCH (e)-[:POSEE]->(h:HistoriaAcademica)
OPTIONAL MATCH (h)-[:TIENE_CONFIABILIDAD]->(conf:ConfiabilidadDato)
MATCH (pl:ParametroModelo {id: 'corte_alfa_llave'}), (pu:ParametroModelo {id: 'corte_alfa_urgencia'})
RETURN {
  estudiante: e {.legajo, .nombre, .anio_ingreso},
  consulta: q.id, periodo: per.id, fecha_referencia: toString(per.fecha_inicio),
  estado_consulta: q.estado, corte_en: q.corte_en,
  solicitud_de_datos: CASE WHEN sol IS NULL THEN null ELSE {ambito: sol.ambito, motivo: sol.motivo, faltantes: sol.faltantes,
                      reglas: coalesce([(sol)-[:JUSTIFICADO_POR]->(r:Regla) | r.id], [])} END,
  confiabilidad_del_dato: CASE WHEN conf IS NULL THEN null ELSE {etiqueta: conf.etiqueta, valor: conf.valor} END,
  horizonte_meses: $horizonte_meses,
  regularidades: [(h)-[:REGISTRA]->(ea:EstadoAcademico)-[:SUSTENTADO_POR]->(rg:Regularidad)
                  WHERE $horizonte_meses IS NULL OR coalesce(rg.meses_para_vencer, 0) <= $horizonte_meses |
                  {asignatura: head([(ea)-[:REFIERE_A]->(a:Asignatura) | a.nombre]), vencimiento: toString(rg.fecha_vencimiento),
                   vigente: rg.vigente, final_rendido: rg.final_rendido, meses_para_vencer: rg.meses_para_vencer,
                   proximidad: head([(m:Medicion)-[:SOBRE]->(rg) | [(m)-[p:PERTENECE]->(t:TerminoLinguistico) |
                                     {etiqueta: t.nombre, mu: p.mu}]]),
                   urgencia: head([(rg)-[:GENERA]->(u:UrgenciaVencimiento) | {grado: u.grado, severidad: u.severidad,
                                   a_confirmar: u.a_confirmar}]),
                   vencida_por: head([(ev:VencimientoRegularidad)-[:INVALIDA]->(rg) | {fecha: toString(ev.fecha),
                                      regla: head([(ev)-[:JUSTIFICADO_POR]->(r:Regla) | r.id])}])}],
  advertencias: [(q)-[:PRODUCE]->(adv:Advertencia) WHERE adv.tipo = 'perdida_regularidad' | {tipo: adv.tipo,
                 mensaje: adv.mensaje, severidad: adv.severidad,
                 asignatura: head([(adv)-[:SOBRE]->(a:Asignatura) | a.nombre])}],
  corte_alfa_urgencia: pu.valor,
  reglas: COLLECT { MATCH (r:Regla) WHERE r.id IN ['H-01', 'E-07d'] RETURN r {.id, .enunciado, .estado} }
        + coalesce([(sol)-[:JUSTIFICADO_POR]->(r:Regla) | r {.id, .enunciado, .estado}], [])
} AS resultado
;

// ================================================================================================
// M3_Q3_ARRASTRES
// ================================================================================================
MATCH (e:Estudiante {legajo: $legajo})<-[:SOLICITADA_POR]-(q:Consulta)-[:REFERIDA_A]->(per:Periodo)
WITH e, q, per ORDER BY q.fecha DESC LIMIT 1
OPTIONAL MATCH (q)-[:PRODUCE]->(rr:ResultadoRiesgo)
OPTIONAL MATCH (rr)-[:ESTIMA]->(rk:RiesgoAtraso)
OPTIONAL MATCH (q)-[:PRODUCE]->(sol:SolicitudDatos)
OPTIONAL MATCH (e)-[:POSEE]->(h:HistoriaAcademica)
OPTIONAL MATCH (h)-[:TIENE_CONFIABILIDAD]->(conf:ConfiabilidadDato)
MATCH (pl:ParametroModelo {id: 'corte_alfa_llave'}), (pu:ParametroModelo {id: 'corte_alfa_urgencia'})
RETURN {
  estudiante: e {.legajo, .nombre, .anio_ingreso},
  consulta: q.id, periodo: per.id, fecha_referencia: toString(per.fecha_inicio),
  estado_consulta: q.estado, corte_en: q.corte_en,
  solicitud_de_datos: CASE WHEN sol IS NULL THEN null ELSE {ambito: sol.ambito, motivo: sol.motivo, faltantes: sol.faltantes,
                      reglas: coalesce([(sol)-[:JUSTIFICADO_POR]->(r:Regla) | r.id], [])} END,
  confiabilidad_del_dato: CASE WHEN conf IS NULL THEN null ELSE {etiqueta: conf.etiqueta, valor: conf.valor} END,
  nivel_nominal: rr.nivel_nominal, nivel_alcanzado: rr.nivel_alcanzado, corte_alfa_llave: pl.valor,
  arrastres: [(rr)-[:IDENTIFICA]->(f:Arrastre)-[:AFECTA_A]->(a:Asignatura) | {asignatura: a.nombre, estado: f.estado_asignatura,
              nivel: head([(a)-[:PERTENECE_A]->(n:Nivel) | n.numero]),
              descendientes: a.cant_descendientes, grado_llave: a.grado_llave, es_llave: a.grado_llave >= pl.valor,
              criticidad: head([(m:Medicion)-[:SOBRE]->(a) WHERE m.variable = 'criticidad_estructural' |
                                [(m)-[p:PERTENECE]->(t:TerminoLinguistico) | {etiqueta: t.nombre, mu: p.mu}]])}],
  reglas: COLLECT { MATCH (r:Regla) WHERE r.id IN ['E-01', 'E-02', 'E-03', 'E-04'] RETURN r {.id, .enunciado, .estado} }
        + coalesce([(sol)-[:JUSTIFICADO_POR]->(r:Regla) | r {.id, .enunciado, .estado}], [])
} AS resultado
;

// ================================================================================================
// M3_Q4_CRITICIDAD
// ================================================================================================
MATCH (pl:ParametroModelo {id: 'corte_alfa_llave'})
UNWIND $codigos AS c
MATCH (a:Asignatura {codigo: c})
OPTIONAL MATCH (m:Medicion {variable: 'criticidad_estructural'})-[:SOBRE]->(a)
WITH pl, a, m ORDER BY a.codigo
WITH pl, collect({
  asignatura: a.nombre, codigo: a.codigo, sigla: a.sigla, dictado: a.dictado,
  nivel: head([(a)-[:PERTENECE_A]->(n:Nivel) | n.numero]),
  descendientes: a.cant_descendientes, grado_llave: a.grado_llave, es_llave: a.grado_llave >= pl.valor,
  criticidad: [(m)-[p:PERTENECE]->(t:TerminoLinguistico) | {etiqueta: t.nombre, mu: p.mu}],
  habilita_directamente: [(d:Asignatura)-[:EXIGE]->(k:Correlatividad)-[:APUNTA_A]->(a) | d.nombre + ' (exige ' + k.tipo + ')'],
  requiere: [(a)-[:EXIGE]->(k:Correlatividad)-[:APUNTA_A]->(r:Asignatura) | r.nombre + ' (' + k.tipo + ')'],
  llave_con_umbral_nitido_PG1: a.cant_descendientes >= 3}) AS asignaturas
RETURN {
  asignaturas: asignaturas,
  corte_alfa_llave: pl.valor,
  reglas: COLLECT { MATCH (r:Regla) WHERE r.id IN ['E-03', 'E-04'] RETURN r {.id, .enunciado, .estado} }
} AS resultado
;

// ================================================================================================
// M3_Q5_RIESGO_SIMULADO
// ================================================================================================
MATCH (e:Estudiante {legajo: $legajo})<-[:SOLICITADA_POR]-(q:Consulta)-[:REFERIDA_A]->(per:Periodo)
WITH e, q, per ORDER BY q.fecha DESC LIMIT 1
OPTIONAL MATCH (q)-[:PRODUCE]->(rr:ResultadoRiesgo)
OPTIONAL MATCH (rr)-[:ESTIMA]->(rk:RiesgoAtraso)
OPTIONAL MATCH (q)-[:PRODUCE]->(sol:SolicitudDatos)
OPTIONAL MATCH (e)-[:POSEE]->(h:HistoriaAcademica)
OPTIONAL MATCH (h)-[:TIENE_CONFIABILIDAD]->(conf:ConfiabilidadDato)
MATCH (pl:ParametroModelo {id: 'corte_alfa_llave'}), (pu:ParametroModelo {id: 'corte_alfa_urgencia'})
MATCH (tr:TerminoLinguistico {variable: 'riesgo_atraso'})
WITH e, q, per, rr, rk, sol, conf, pl, pu, h, collect(tr {.nombre, .funcion, .centro, .sigma}) AS TR
MATCH (tb:TerminoLinguistico {id: 'capacidad_disponible:baja'})
MATCH (rd:ReglaDifusa)<-[:CONTIENE]-(:SistemaDifuso {id: 'SD-M3-RIESGO'}), (rd)-[:CONSECUENTE]->(tc:TerminoLinguistico)
WITH e, q, per, rr, rk, sol, conf, pl, pu, h, TR, tb,
     collect({id: rd.id, enunciado: rd.enunciado, estado: rd.estado, consecuente: tc.nombre}) AS RD
// Entradas medidas en PG2: arrastre (peor caso por descendientes), proximidad y capacidad
WITH *, coalesce([(rr)-[:IDENTIFICA]->(:Arrastre)-[:AFECTA_A]->(a:Asignatura) | a], []) AS arr
WITH *, reduce(b = null, a IN arr | CASE WHEN b IS NULL OR a.cant_descendientes > b.cant_descendientes THEN a ELSE b END) AS peor
WITH *, CASE WHEN size(arr) > 0 THEN 1.0 ELSE 0.0 END AS A,
     CASE WHEN peor IS NULL THEN [] ELSE head([(m:Medicion)-[:SOBRE]->(peor) WHERE m.variable = 'criticidad_estructural' |
       [(m)-[p:PERTENECE]->(t:TerminoLinguistico) | {etiqueta: t.nombre, mu: p.mu}]]) END AS CR,
     head([(q)-[:MIDE]->(m:Medicion {variable: 'proximidad_vencimiento'}) | {valor: m.valor,
       grados: [(m)-[p:PERTENECE]->(t:TerminoLinguistico) | {etiqueta: t.nombre, mu: p.mu}]}]) AS PX,
     head([(m:Medicion)-[:MODULA]->(rk) | {valor: m.valor,
       mu_baja: head([(m)-[p:PERTENECE]->(t:TerminoLinguistico {nombre: 'baja'}) | p.mu])}]) AS CAP
WITH *, coalesce(head([c IN CR WHERE c.etiqueta = 'alta' | c.mu]), 0.0) AS cA,
     reduce(mm = 0.0, c IN CR | CASE WHEN c.etiqueta IN ['baja', 'media'] AND c.mu > mm THEN c.mu ELSE mm END) AS cBM,
     coalesce(head([p IN PX.grados WHERE p.etiqueta = 'inminente' | p.mu]), 0.0) AS pin,
     coalesce(head([p IN PX.grados WHERE p.etiqueta = 'cercana' | p.mu]), 0.0) AS pce,
     coalesce(head([p IN PX.grados WHERE p.etiqueta = 'lejana' | p.mu]), 1.0) AS lej,
     CASE WHEN $horas_hipoteticas IS NULL THEN coalesce(CAP.mu_baja, 0.0)
          ELSE (CASE WHEN tb.funcion = 'crisp' THEN (CASE WHEN toFloat($horas_hipoteticas) = tb.centro THEN 1.0 ELSE 0.0 END) WHEN (tb.funcion = 'gauss_hombro_izq' AND toFloat($horas_hipoteticas) <= tb.centro) OR (tb.funcion = 'gauss_hombro_der' AND toFloat($horas_hipoteticas) >= tb.centro) THEN 1.0 ELSE exp(-((toFloat($horas_hipoteticas) - tb.centro)^2) / (2.0 * tb.sigma^2)) END) END AS capb
WITH *, reduce(mx = 0.0, v IN [pin, pce] | CASE WHEN v > mx THEN v ELSE mx END) AS urg
WITH *, [r IN RD | r {.*,
  alfa: CASE r.id
    WHEN 'E-08d' THEN reduce(mn = 1.0, v IN [A, cA] | CASE WHEN v < mn THEN v ELSE mn END)
    WHEN 'E-09d' THEN reduce(mn = 1.0, v IN [A, urg, capb] | CASE WHEN v < mn THEN v ELSE mn END)
    WHEN 'E-10d' THEN reduce(mn = 1.0, v IN [1.0 - A, urg] | CASE WHEN v < mn THEN v ELSE mn END)
    WHEN 'E-11d' THEN reduce(mn = 1.0, v IN [1.0 - A, lej] | CASE WHEN v < mn THEN v ELSE mn END)
    WHEN 'E-12d' THEN reduce(mn = 1.0, v IN [A, cBM] | CASE WHEN v < mn THEN v ELSE mn END)
    ELSE 0.0 END,
  t: head([t IN TR WHERE t.nombre = r.consecuente])}] AS acts
// Implicación MIN (recorte), agregación MAX y centroide sobre 1001 puntos de [0, 1]
WITH *, [i IN range(0, 1000) | toFloat(i) / 1000.0] AS Y
WITH *, [y IN Y | reduce(m = 0.0, r IN acts |
  CASE WHEN reduce(mn = 1.0, v IN [r.alfa, (CASE WHEN r.t.funcion = 'crisp' THEN (CASE WHEN y = r.t.centro THEN 1.0 ELSE 0.0 END) WHEN (r.t.funcion = 'gauss_hombro_izq' AND y <= r.t.centro) OR (r.t.funcion = 'gauss_hombro_der' AND y >= r.t.centro) THEN 1.0 ELSE exp(-((y - r.t.centro)^2) / (2.0 * r.t.sigma^2)) END)] | CASE WHEN v < mn THEN v ELSE mn END) > m THEN reduce(mn = 1.0, v IN [r.alfa, (CASE WHEN r.t.funcion = 'crisp' THEN (CASE WHEN y = r.t.centro THEN 1.0 ELSE 0.0 END) WHEN (r.t.funcion = 'gauss_hombro_izq' AND y <= r.t.centro) OR (r.t.funcion = 'gauss_hombro_der' AND y >= r.t.centro) THEN 1.0 ELSE exp(-((y - r.t.centro)^2) / (2.0 * r.t.sigma^2)) END)] | CASE WHEN v < mn THEN v ELSE mn END) ELSE m END)] AS agg
WITH *, reduce(s = 0.0, i IN range(0, 1000) | s + agg[i] * Y[i]) AS num, reduce(s = 0.0, v IN agg | s + v) AS den
WITH *, CASE WHEN den > 0 THEN num / den ELSE null END AS yc
WITH *, [t IN TR | {etiqueta: t.nombre, mu: (CASE WHEN t.funcion = 'crisp' THEN (CASE WHEN yc = t.centro THEN 1.0 ELSE 0.0 END) WHEN (t.funcion = 'gauss_hombro_izq' AND yc <= t.centro) OR (t.funcion = 'gauss_hombro_der' AND yc >= t.centro) THEN 1.0 ELSE exp(-((yc - t.centro)^2) / (2.0 * t.sigma^2)) END)}] AS grados_salida
WITH *, reduce(b = null, g IN grados_salida | CASE WHEN b IS NULL OR g.mu > b.mu THEN g ELSE b END).etiqueta AS etiqueta_salida
RETURN {
  estudiante: e {.legajo, .nombre, .anio_ingreso},
  consulta: q.id, periodo: per.id, fecha_referencia: toString(per.fecha_inicio),
  estado_consulta: q.estado, corte_en: q.corte_en,
  solicitud_de_datos: CASE WHEN sol IS NULL THEN null ELSE {ambito: sol.ambito, motivo: sol.motivo, faltantes: sol.faltantes,
                      reglas: coalesce([(sol)-[:JUSTIFICADO_POR]->(r:Regla) | r.id], [])} END,
  confiabilidad_del_dato: CASE WHEN conf IS NULL THEN null ELSE {etiqueta: conf.etiqueta, valor: conf.valor} END,
  escenario_hipotetico: $horas_hipoteticas IS NOT NULL,
  capacidad_disponible: {horas_registradas: CAP.valor, mu_baja_registrada: CAP.mu_baja,
                         horas_hipoteticas: $horas_hipoteticas, mu_baja_usada: capb},
  entradas_inferencia: {arrastre: A, peor_arrastre: peor.nombre, descendientes_peor_arrastre: peor.cant_descendientes,
                        criticidad_alta: cA, criticidad_baja_o_media: cBM, meses_regularidad_mas_proxima: PX.valor,
                        urgencia: urg, proximidad_lejana: lej, capacidad_baja: capb},
  reglas_difusas: [r IN acts | {id: r.id, enunciado: r.enunciado, estado: r.estado, consecuente: r.consecuente, alfa: r.alfa}],
  riesgo_atraso: CASE WHEN rk IS NULL OR yc IS NULL THEN null ELSE {valor: yc, etiqueta: etiqueta_salida, grados: grados_salida} END,
  riesgo_registrado_en_PG2: CASE WHEN rk IS NULL THEN null ELSE {valor: rk.valor, etiqueta: rk.etiqueta} END,
  reglas: COLLECT { MATCH (r:Regla) WHERE r.id IN ['E-07d', 'E-13'] RETURN r {.id, .enunciado, .estado} }
} AS resultado
;

// ================================================================================================
// M4_PLAN
// ================================================================================================
MATCH (e:Estudiante {legajo: $legajo})<-[:SOLICITADA_POR]-(q:Consulta)-[:REFERIDA_A]->(per:Periodo)
OPTIONAL MATCH (q)-[:PRODUCE]->(pc:PlanCursado)
OPTIONAL MATCH (q)-[:PRODUCE]->(cd:ConfiabilidadDato)
OPTIONAL MATCH (q)-[:PRODUCE]->(rk:RiesgoAtraso)
OPTIONAL MATCH (q)-[:PRODUCE]->(ad:AdecuacionPlan)
OPTIONAL MATCH (q)-[:PRODUCE]->(ev:EvaluacionCarga)-[:DETERMINA]->(ta:TamanioAdmisible)
OPTIONAL MATCH (q)-[:PRODUCE]->(rs:RiesgoSobrecarga)
RETURN {
  estudiante: e.nombre, legajo: e.legajo, periodo: per.id, estado_consulta: q.estado, corte_en: q.corte_en,
  confiabilidad: {etiqueta: cd.etiqueta, valor: round(cd.valor, 2), antecedentes_sin_dato: cd.antecedentes_sin_dato},
  capacidad: {carga_h: round(ev.carga_horas, 1), capacidad_h: ev.capacidad_horas, holgura_h: round(ev.holgura_horas, 1),
              tamano_base: ta.base, tamano_admisible: ta.valor, tope: ta.tope_declarado,
              ajustes: [(aj:Ajuste)-[:REDUCE]->(ta) | {tipo: [l IN labels(aj) WHERE l STARTS WITH 'AjustePor'][0],
                                                      unidades: aj.unidades, causa: aj.causa}],
              riesgo_sobrecarga: {etiqueta: rs.etiqueta, valor: round(rs.valor, 2),
                                  reglas: [(rs)-[j:JUSTIFICADO_POR]->(r:ReglaDifusa) | {regla: r.id, alfa: round(j.alfa, 2)}]}},
  plan: COLLECT {
    MATCH (pc)-[x:INCLUYE]->(i:ItemCandidato)
    RETURN {
          orden: x.orden, alcance: i.alcance, asignatura: i.asignatura, rango: i.rango,
          criterio: [(i)-[:TIENE_PRIORIDAD]->(pr) | pr.criterio][0],
          reglas: [(i)-[:TIENE_PRIORIDAD]->(:Prioridad)-[:JUSTIFICADO_POR]->(r) | r.id]
                  + [(d:Habilitacion)-[:ALIMENTA]->(i) | [(d)-[:JUSTIFICADO_POR]->(r2) | r2.id]][0],
          fundamentos: [(f:FactorDeRiesgo)-[:FUNDAMENTA]->(:Prioridad)<-[:TIENE_PRIORIDAD]-(i) |
                        {factor: f.id, grado: round(f.grado, 2)}]} AS item
    ORDER BY x.orden},
  excluidos: [(pc)-[x:EXCLUYE]->(i:ItemCandidato) | {asignatura: i.asignatura, alcance: i.alcance, causa: x.causa,
              empate_persistente: i.empate_persistente, regla_desempate: i.regla_desempate,
              habilitada_por: [(d:Habilitacion)-[:ALIMENTA]->(i) | [(d)-[:JUSTIFICADO_POR]->(r2) | r2.id]][0],
              reglas: [(pc)-[:JUSTIFICADO_POR]->(r3) | r3.id]}],
  advertencias: [(q)-[:PRODUCE]->(a:Advertencia) | {tipo: a.tipo, mensaje: a.mensaje,
                 reglas: [(a)-[:JUSTIFICADO_POR]->(r) | r.id]}],
  riesgo: {etiqueta: rk.etiqueta, valor: round(rk.valor, 2), salvedad: rk.salvedad,
           antecedentes_sin_dato: rk.antecedentes_sin_dato,
           reglas: [(rk)-[j:JUSTIFICADO_POR]->(r:ReglaDifusa) | {regla: r.id, alfa: round(j.alfa, 2)}]},
  adecuacion: {etiqueta: ad.etiqueta, valor: round(ad.valor, 2), antecedentes_sin_dato: ad.antecedentes_sin_dato},
  glosario_reglas: COLLECT {
    MATCH (q)-[:PRODUCE]->(:Conclusion)-[:JUSTIFICADO_POR]->(r:Regla)
    RETURN DISTINCT {id: r.id, enunciado: r.enunciado, estado: r.estado} AS regla
    ORDER BY regla.id}
} AS traza
;

// ================================================================================================
// M4_PLAN_ASIGNATURA
// ================================================================================================
MATCH (e:Estudiante {legajo: $legajo})<-[:SOLICITADA_POR]-(q:Consulta)-[:PRODUCE]->(pc:PlanCursado)
RETURN {
  periodo: pc.periodo, tamano_efectivo: pc.tamano_efectivo,
  tamano_admisible: [(ta:TamanioAdmisible)-[:LIMITA]->(pc) | ta.valor][0],
  tope_declarado: [(ta:TamanioAdmisible)-[:LIMITA]->(pc) | ta.tope_declarado][0],
  items: [(pc)-[x:INCLUYE|EXCLUYE]->(i:ItemCandidato)-[:SOBRE]->(:Asignatura {codigo: $codigo}) |
          {decision: CASE type(x) WHEN 'INCLUYE' THEN 'incluida' ELSE 'excluida' END,
           asignatura: i.asignatura, alcance: i.alcance, orden: i.orden, causa: x.causa, rango: i.rango,
           criterio: [(i)-[:TIENE_PRIORIDAD]->(pr) | pr.criterio][0],
           empate_persistente: i.empate_persistente, regla_desempate: i.regla_desempate}],
  reglas: [(pc)-[:JUSTIFICADO_POR]->(r) | {id: r.id, enunciado: r.enunciado, estado: r.estado}]
          + COLLECT {
              MATCH (pc)-[:INCLUYE|EXCLUYE]->(i2:ItemCandidato)-[:SOBRE]->(:Asignatura {codigo: $codigo})
              MATCH (r4:Regla {id: i2.regla_desempate})
              RETURN DISTINCT {id: r4.id, enunciado: r4.enunciado, estado: r4.estado} AS regla}
} AS traza
;

