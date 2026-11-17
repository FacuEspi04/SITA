// Auditoría del dictamen de Lucía (48115) sobre Inteligencia Artificial (código 31), caso E2E-01.
// Pegar en Neo4j Browser / Aura Query. Primero los parámetros, después cada consulta.

:params {legajo: '48115', codigo: 31, alcance: 'cursar'}

// 1) Recorrido tabular: qué relación se recorrió para cada condición y con qué estado
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

// 2) Subgrafo para la captura del video
MATCH (e:Estudiante)<-[:SOLICITADA_POR]-(q:Consulta)-[:PRODUCE]->(d:Dictamen {alcance: $alcance})
      -[:SOBRE]->(a:Asignatura {codigo: $codigo})
WHERE toString(e.legajo) = $legajo
OPTIONAL MATCH p1 = (d)-[:ORIGINADO_POR|VERIFICA|CAUSA_RAIZ]->(:Correlatividad)-[:APUNTA_A]->(:Asignatura)
OPTIONAL MATCH p2 = (d)-[:JUSTIFICADO_POR]->(:Regla)
OPTIONAL MATCH p3 = (d)-[:HEREDA_DE]->(:Dictamen)-[:SOBRE]->(:Asignatura)
RETURN e, q, d, a, p1, p2, p3
;
