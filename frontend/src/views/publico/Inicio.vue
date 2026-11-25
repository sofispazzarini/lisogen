<script setup lang="ts">
/** Home público de LisoGen: portada, qué ofrece, el recorrido real de un estudio, el laboratorio, el
 * Laboratorio Central y preguntas frecuentes. Los textos describen lo que hace el sistema (reglas de
 * domain/reglas.py: precio, urgencias, lotes, turnos). Las ilustraciones son SVG propios. */

// Doble hélice de ADN de la portada (misma fórmula que la maqueta)
const ANCHO_HELICE = 300
const ALTO_HELICE = 440
const helice = (() => {
  const cx = 150
  const amplitud = 84
  const n = 96
  const arriba = 18
  const abajo = 422
  const a: [number, number][] = []
  const b: [number, number][] = []
  for (let i = 0; i <= n; i++) {
    const t = i / n
    const y = arriba + (abajo - arriba) * t
    const fase = t * Math.PI * 5
    a.push([cx + amplitud * Math.sin(fase), y])
    b.push([cx - amplitud * Math.sin(fase), y])
  }
  const trazo = (puntos: [number, number][]) =>
    puntos.map((p, i) => `${i ? 'L' : 'M'}${p[0].toFixed(1)} ${p[1].toFixed(1)}`).join(' ')
  const peldanos: { a: [number, number]; b: [number, number] }[] = []
  for (let i = 4; i < n; i += 6) peldanos.push({ a: a[i]!, b: b[i]! })
  return { a: trazo(a), b: trazo(b), peldanos }
})()

// Esquema de La Plata: cuadrícula, las diagonales y la sede marcada
const ANCHO_PLANO = 480
const ALTO_PLANO = 300
const verticales = Array.from({ length: 11 }, (_, i) => 40 * (i + 1))
const horizontales = Array.from({ length: 7 }, (_, i) => 40 * (i + 1))

const AREAS = [
  {
    estilo: 'clara',
    antetitulo: 'El estudio que realizamos',
    titulo: 'Exoma clínico',
    texto:
      'Secuenciación del exoma enfocada en los genes de Fabry, Pompe, MPS 1, Gaucher y ASMD, con la opción de evaluar hallazgos secundarios.',
    icono: 'adn',
  },
  {
    estilo: 'oscura',
    antetitulo: 'Para médicos tratantes',
    titulo: 'Solicitud y seguimiento',
    texto:
      'Dan de alta a sus pacientes con los síntomas en SNOMED CT y el familiograma, piden el estudio y consultan el historial de la familia.',
    icono: 'documento',
  },
  {
    estilo: 'oscura',
    antetitulo: 'Para pacientes',
    titulo: 'Tu estudio en línea',
    texto:
      'Pagás o tramitás la cobertura de tu obra social, sacás turno para la extracción y ves el resultado desde tu cuenta.',
    icono: 'tablero',
  },
] as const

const PASOS = [
  {
    nombre: 'Solicitud',
    texto:
      'El médico tratante da de alta al paciente, valida el diagnóstico presuntivo y pide el estudio; los genes salen del catálogo de cada patología.',
  },
  {
    nombre: 'Presupuesto y cobertura',
    texto: 'El laboratorio emite el presupuesto. Si hay obra social, tramita su autorización; si no, el paciente paga desde su cuenta.',
  },
  {
    nombre: 'Turno y extracción',
    texto: 'El paciente elige centro y horario, y recibe la orden de extracción y el consentimiento informado.',
  },
  {
    nombre: 'Traslado y secuenciación',
    texto:
      'Un transportista lleva la muestra al Laboratorio Central. En lotes de 10, con autorización del Ministerio de Salud, viajan a Corea por FedEx.',
  },
  {
    nombre: 'Análisis y resultado',
    texto: 'Un bioinformático clasifica las variantes y el informe queda disponible para el paciente y su médico.',
  },
]

const LABORATORIO = [
  {
    titulo: 'Trazabilidad',
    texto: 'Cada muestra, lote y archivo queda vinculado a su estudio, con el historial de estados y avisos a quienes intervienen.',
  },
  {
    titulo: 'Urgencias',
    texto: 'Si el estudio es de Pompe en un bebé de menos de 4 meses, su lote sale sin esperar las 10 muestras y se analiza primero.',
  },
  {
    titulo: 'Privacidad',
    texto: 'Cada persona ve sólo lo que le corresponde, y cada consulta a una ficha o a un resultado queda registrada (Ley 25.326).',
  },
]

const PREGUNTAS = [
  {
    pregunta: '¿Cómo se solicita un estudio?',
    respuesta:
      'Lo pide tu médico tratante desde LisoGen. Cuando te da de alta, te llega por mail tu usuario y una contraseña provisoria para entrar y seguir el estudio.',
  },
  {
    pregunta: '¿Cuánto cuesta y qué cubre mi obra social?',
    respuesta:
      'El exoma cuesta USD 500 hasta 5 genes y USD 30 por cada gen adicional. Si tenés obra social, el laboratorio tramita su autorización y pagás sólo la parte que no cubre. Si la rechaza, podés pedir una reautorización presentando una decisión judicial. Si tu médico te asignó un cupón, se descuenta al pagar.',
  },
  {
    pregunta: '¿Dónde me hago la extracción?',
    respuesta:
      'Sacás turno desde tu cuenta en el centro de extracción que te quede más cómodo, de lunes a viernes de 9 a 18. El día anterior te llega un recordatorio.',
  },
  {
    pregunta: '¿Qué pasa si la muestra no sirve?',
    respuesta:
      'Si llega con mala calidad o el ADN se desnaturaliza, el laboratorio pide una nueva extracción: sacás otro turno y no pagás de nuevo.',
  },
  {
    pregunta: '¿Cómo me entero del resultado?',
    respuesta:
      'Cuando el bioinformático confirma el análisis, te avisamos y el informe queda en tu cuenta: positivo, negativo o no concluyente. Más adelante tu médico puede pedir un reanálisis sin una nueva extracción.',
  },
  {
    pregunta: '¿Puedo consultar dudas sobre mi patología?',
    respuesta:
      'Sí: desde tu cuenta podés hacerle preguntas al chatbot sobre las cinco patologías. No reemplaza la consulta con tu médico.',
  },
  {
    pregunta: 'Soy profesional, ¿cómo accedo?',
    respuesta:
      'Médicos tratantes, administrativos, bioinformáticos y gerentes médicos se registran desde Ingresar, en la pestaña Registrarse. Los pacientes no se registran: los da de alta su médico.',
  },
]
</script>

<template>
  <div class="inicio">
    <section id="inicio" class="portada">
      <div class="envoltura portada-interior">
        <div>
          <h1>Exoma clínico para patologías lisosomales, de la consulta al resultado.</h1>
          <p class="bajada">
            LisoGen gestiona estudios genéticos para Fabry, Pompe, MPS 1, Gaucher y ASMD. El médico tratante los solicita, el paciente
            los sigue desde su cuenta y el laboratorio acompaña cada etapa hasta el informe.
          </p>
          <RouterLink :to="{ path: '/', hash: '#como-funciona' }" class="boton-claro">Ver el recorrido</RouterLink>
        </div>
        <div class="helice">
          <svg :viewBox="`0 0 ${ANCHO_HELICE} ${ALTO_HELICE}`" role="img" aria-label="Ilustración de una doble hélice de ADN">
            <line
              v-for="(p, i) in helice.peldanos"
              :key="`l${i}`"
              :x1="p.a[0]"
              :y1="p.a[1]"
              :x2="p.b[0]"
              :y2="p.b[1]"
              stroke="rgba(255,255,255,.28)"
              stroke-width="2"
            />
            <path :d="helice.a" fill="none" stroke="#CFE8E4" stroke-width="3.5" stroke-linecap="round" />
            <path :d="helice.b" fill="none" stroke="#7FB0AB" stroke-width="3.5" stroke-linecap="round" />
            <template v-for="(p, i) in helice.peldanos" :key="`c${i}`">
              <circle :cx="p.a[0]" :cy="p.a[1]" r="3.5" fill="#CFE8E4" />
              <circle :cx="p.b[0]" :cy="p.b[1]" r="3.5" fill="#7FB0AB" />
            </template>
          </svg>
        </div>
      </div>
      <RouterLink :to="{ path: '/', hash: '#estudios' }" class="mas" aria-label="Ir a qué ofrece LisoGen">
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M6 9l6 6 6-6" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" />
        </svg>
      </RouterLink>
    </section>

    <section id="estudios" class="bloque centrado">
      <div class="envoltura">
        <h2 class="titulo-bloque">Qué ofrece LisoGen</h2>
        <p class="intro">Un único sistema para todas las personas que intervienen en un estudio: médicos, pacientes y el equipo del laboratorio.</p>
        <div class="tarjetas">
          <article v-for="a in AREAS" :key="a.titulo" class="area" :class="`area--${a.estilo}`">
            <div>
              <p class="antetitulo">{{ a.antetitulo }}</p>
              <h3>{{ a.titulo }}</h3>
            </div>
            <div class="area-cuerpo">
              <svg class="icono" viewBox="0 0 64 64" aria-hidden="true">
                <template v-if="a.icono === 'adn'">
                  <path d="M20 6c0 14 24 18 24 26s-24 12-24 26" />
                  <path d="M44 6c0 14-24 18-24 26s24 12 24 26" />
                  <path d="M24 16h16M26 26h12M26 38h12M24 48h16" />
                </template>
                <template v-else-if="a.icono === 'documento'">
                  <rect x="14" y="8" width="36" height="48" rx="3" />
                  <path d="M22 20h20M22 28h20M22 36h14M22 44h8" />
                </template>
                <template v-else>
                  <rect x="12" y="10" width="40" height="46" rx="4" />
                  <path d="M22 8h20v8H22z" />
                  <path d="M22 34l6 6 14-14" />
                </template>
              </svg>
              <p>{{ a.texto }}</p>
            </div>
          </article>
          <article class="area area--teal">
            <div>
              <p class="antetitulo">Donde llegan las muestras</p>
              <h3>Laboratorio Central</h3>
            </div>
            <div class="area-cuerpo">
              <svg class="icono" viewBox="0 0 64 64" aria-hidden="true">
                <path d="M32 56s-16-14-16-28a16 16 0 1 1 32 0c0 14-16 28-16 28z" />
                <circle cx="32" cy="28" r="5" />
              </svg>
              <div>
                <p>En La Plata recibimos las muestras de todos los centros de extracción, armamos los lotes y coordinamos su envío.</p>
                <RouterLink :to="{ path: '/', hash: '#sede' }" class="enlace-area">Ver ubicación</RouterLink>
              </div>
            </div>
          </article>
        </div>
      </div>
    </section>

    <section id="como-funciona" class="bloque centrado">
      <div class="envoltura">
        <h2 class="titulo-bloque">Un estudio, de principio a fin</h2>
        <p class="intro">Cada etapa queda registrada y cada persona ve en qué punto está el estudio: el médico, el paciente y el laboratorio.</p>
        <ol class="pasos">
          <li v-for="p in PASOS" :key="p.nombre">
            <h3 class="paso-nombre">{{ p.nombre }}</h3>
            <p>{{ p.texto }}</p>
          </li>
        </ol>
      </div>
    </section>

    <section id="laboratorio" class="banda">
      <div class="envoltura banda-interior">
        <div class="banda-caja">
          <h2 class="titulo-bloque">El laboratorio</h2>
          <p class="cuerpo">
            LisoGen registra cada paso del estudio en un solo lugar. Cada rol ve lo que le toca: el médico, a sus pacientes; el paciente,
            su estudio; el laboratorio, la logística, los lotes y el análisis bioinformático.
          </p>
          <div class="filas">
            <div v-for="f in LABORATORIO" :key="f.titulo" class="fila-lab">
              <h3>{{ f.titulo }}</h3>
              <p>{{ f.texto }}</p>
            </div>
          </div>
        </div>
        <div class="tubo" aria-hidden="true">
          <svg viewBox="0 0 140 320">
            <path d="M40 28V248Q40 296 70 296Q100 296 100 248V28" fill="none" stroke="currentColor" stroke-width="6" stroke-linejoin="round" />
            <path d="M46 150H94V248Q94 290 70 290Q46 290 46 248Z" fill="currentColor" opacity=".85" />
            <line x1="32" y1="28" x2="108" y2="28" stroke="currentColor" stroke-width="6" stroke-linecap="round" />
            <circle cx="64" cy="200" r="4" fill="#fff" opacity=".7" />
            <circle cx="80" cy="236" r="3" fill="#fff" opacity=".7" />
            <circle cx="70" cy="262" r="2.5" fill="#fff" opacity=".7" />
          </svg>
        </div>
      </div>
    </section>

    <section id="sede" class="bloque">
      <div class="envoltura sede">
        <div>
          <h2 class="titulo-bloque">Laboratorio Central en La Plata</h2>
          <p>
            Las muestras de los centros de extracción llegan al Laboratorio Central. Desde ahí se arman los lotes, se programa el retiro
            con FedEx y se reciben los datos de la secuenciación.
          </p>
          <p class="lugar">Calle 62 N.º 555, La Plata, provincia de Buenos Aires</p>
        </div>
        <div class="plano">
          <svg :viewBox="`0 0 ${ANCHO_PLANO} ${ALTO_PLANO}`" role="img" aria-label="Esquema de La Plata con el Laboratorio Central marcado">
            <rect x="0" y="0" :width="ANCHO_PLANO" :height="ALTO_PLANO" rx="10" class="plano-fondo" />
            <line v-for="x in verticales" :key="`v${x}`" :x1="x" y1="0" :x2="x" :y2="ALTO_PLANO" class="plano-calle" stroke-width="1" />
            <line v-for="y in horizontales" :key="`h${y}`" x1="0" :y1="y" :x2="ANCHO_PLANO" :y2="y" class="plano-calle" stroke-width="1" />
            <line x1="0" :y1="ALTO_PLANO" :x2="ANCHO_PLANO" y2="0" class="plano-diagonal" stroke-width="2" opacity="0.45" />
            <line x1="0" y1="120" x2="180" y2="0" class="plano-diagonal" stroke-width="2" opacity="0.25" />
            <circle cx="290" cy="150" r="14" class="plano-punto" opacity="0.12" />
            <circle cx="290" cy="150" r="8" class="plano-punto plano-punto--borde" stroke-width="3" />
            <text x="312" y="146" class="plano-texto" font-size="14" font-weight="600">Laboratorio Central</text>
            <text x="312" y="166" class="plano-texto plano-texto--suave" font-size="12">Calle 62 N.º 555</text>
          </svg>
        </div>
      </div>
    </section>

    <section id="preguntas" class="bloque centrado">
      <div class="envoltura">
        <h2 class="titulo-bloque">Preguntas frecuentes</h2>
        <div class="faq">
          <details v-for="p in PREGUNTAS" :key="p.pregunta">
            <summary>{{ p.pregunta }}</summary>
            <p>{{ p.respuesta }}</p>
          </details>
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
.envoltura { width: min(1080px, 100% - 48px); margin: 0 auto; }
section[id] { scroll-margin-top: 84px; }

/* Portada en bloque de color */
.portada { position: relative; overflow: hidden; background: var(--color-primario-profundo); color: #fff; }
.portada-interior {
  display: grid;
  grid-template-columns: minmax(0, 1.1fr) minmax(0, 0.9fr);
  align-items: center;
  gap: 40px;
  min-height: min(86vh, 720px);
  padding: 72px 0 104px;
}
.portada h1 {
  margin: 0 0 22px;
  color: #fff;
  font: 600 clamp(36px, 4.6vw, 56px) / 1.06 var(--fuente-titulos);
  letter-spacing: -0.02em;
  text-wrap: balance;
}
.bajada { margin: 0; max-width: 46ch; font-size: 18px; color: rgb(255 255 255 / 88%); }
.boton-claro {
  display: inline-block;
  margin-top: 32px;
  padding: 11px 18px;
  border: 1px solid rgb(255 255 255 / 70%);
  border-radius: var(--radio-chico);
  color: #fff;
  font-weight: 600;
  text-decoration: none;
}
.boton-claro:hover { background: rgb(255 255 255 / 12%); }
.helice svg { display: block; width: min(300px, 100%); height: auto; margin-left: auto; }
.mas {
  position: absolute;
  left: 50%;
  bottom: 24px;
  transform: translateX(-50%);
  display: grid;
  place-items: center;
  width: 46px;
  height: 46px;
  border: 1.5px solid rgb(255 255 255 / 75%);
  border-radius: 50%;
  color: #fff;
}
.mas svg { width: 20px; height: 20px; }
.portada :focus-visible { outline-color: #fff; }

/* Secciones */
.bloque { padding: 96px 0; }
.titulo-bloque {
  margin: 0 0 14px;
  color: var(--color-primario);
  font: 700 clamp(26px, 3vw, 34px) / 1.2 var(--fuente);
  letter-spacing: 0.01em;
  text-transform: uppercase;
  text-wrap: balance;
}
.intro { margin: 0 0 52px; max-width: 60ch; color: var(--color-texto-suave); }
.centrado { text-align: center; }
.centrado .intro { margin-left: auto; margin-right: auto; }

/* Tarjetas 2x2 */
.tarjetas { display: grid; grid-template-columns: 1fr 1fr; gap: 24px; max-width: 920px; margin: 0 auto; text-align: left; }
.area { display: flex; flex-direction: column; gap: 24px; min-height: 270px; padding: 36px; border-radius: 6px; }
.area--clara { background: var(--color-niebla); color: var(--color-texto); }
.area--oscura { background: var(--color-pizarra); color: #fff; }
.area--teal { background: var(--color-primario-profundo); color: #fff; }
.antetitulo { margin: 0; font-size: 15px; font-weight: 500; }
.area--clara .antetitulo { color: var(--color-primario); }
.area--oscura .antetitulo { color: #9ed6cf; }
.area--teal .antetitulo { color: #cfede8; }
.area h3 { margin: 0; font: 700 22px/1.2 var(--fuente); letter-spacing: 0.01em; text-transform: uppercase; }
.area-cuerpo { display: flex; align-items: center; gap: 22px; margin-top: auto; }
.area-cuerpo p { margin: 0; font-size: 15px; line-height: 1.55; }
.icono { flex: none; width: 64px; height: 64px; fill: none; stroke: currentColor; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; }
.enlace-area { display: inline-block; margin-top: 10px; color: #fff; font-weight: 600; }
.area--oscura :focus-visible,
.area--teal :focus-visible { outline-color: #fff; }

/* Recorrido de un estudio */
.pasos {
  position: relative;
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 28px;
  margin: 0;
  padding: 0;
  list-style: none;
  text-align: left;
}
.pasos::before { content: ''; position: absolute; left: 0; right: 0; top: 9px; height: 1px; background: var(--color-borde); }
.pasos li { position: relative; padding-top: 36px; }
.pasos li::before {
  content: '';
  position: absolute;
  left: 0;
  top: 1px;
  width: 16px;
  height: 16px;
  border: 2px solid var(--color-primario);
  border-radius: 50%;
  background: var(--color-fondo);
}
.paso-nombre { margin: 0 0 8px; font: 600 19px/1.25 var(--fuente-titulos); }
.pasos p { margin: 0; font-size: 14.5px; color: var(--color-texto-suave); }

/* Banda del laboratorio */
.banda { padding: 96px 0; background: var(--color-banda); scroll-margin-top: 84px; }
.banda-interior { display: grid; grid-template-columns: minmax(0, 1fr) 220px; align-items: center; gap: 56px; }
.banda-caja { padding: 44px; border-radius: 6px; background: var(--color-superficie); }
.banda-caja .titulo-bloque { font-size: clamp(24px, 2.6vw, 30px); }
.cuerpo { max-width: 56ch; margin: 0 0 28px; }
.filas { border-top: 1px solid var(--color-borde); }
.fila-lab { display: grid; grid-template-columns: 170px minmax(0, 1fr); gap: 24px; padding: 18px 0; border-bottom: 1px solid var(--color-borde); }
.fila-lab h3 { margin: 0; font: 600 18px/1.3 var(--fuente-titulos); }
.fila-lab p { margin: 0; font-size: 15px; color: var(--color-texto-suave); }
.tubo { color: var(--color-primario); }
.tubo svg { display: block; width: 100%; height: auto; }

/* Sede */
.sede { display: grid; grid-template-columns: minmax(0, 0.9fr) minmax(0, 1.1fr); align-items: center; gap: 64px; }
.sede p { max-width: 52ch; margin: 0 0 14px; color: var(--color-texto-suave); }
.sede .lugar { margin: 22px 0 0; font-weight: 600; color: var(--color-texto); }
.plano { padding: 14px; border: 1px solid var(--color-borde); border-radius: var(--radio); background: var(--color-superficie); }
.plano svg { display: block; width: 100%; height: auto; }
.plano-fondo { fill: var(--color-superficie-2); }
.plano-calle { stroke: var(--color-borde); }
.plano-diagonal { stroke: var(--color-primario); }
.plano-punto { fill: var(--color-primario); }
.plano-punto--borde { stroke: var(--color-superficie); }
.plano-texto { fill: var(--color-texto); font-family: var(--fuente); }
.plano-texto--suave { fill: var(--color-texto-suave); }

/* Preguntas frecuentes */
.faq { max-width: 760px; margin: 0 auto; text-align: left; border-top: 1px solid var(--color-borde); }
.faq details { border-bottom: 1px solid var(--color-borde); }
.faq summary {
  position: relative;
  padding: 20px 36px 20px 0;
  font: 600 18px/1.35 var(--fuente-titulos);
  list-style: none;
  cursor: pointer;
}
.faq summary::-webkit-details-marker { display: none; }
.faq summary::after { content: '+'; position: absolute; right: 4px; top: 16px; color: var(--color-primario); font: 400 22px/1 var(--fuente); }
.faq details[open] summary::after { content: '–'; }
.faq details p { max-width: 60ch; margin: 0 0 20px; color: var(--color-texto-suave); }

@media (max-width: 920px) {
  .portada-interior { grid-template-columns: 1fr; gap: 28px; min-height: 0; padding: 48px 0 120px; }
  .helice svg { width: 200px; margin: 0 auto; }
  .bloque { padding: 72px 0; }
  .tarjetas { grid-template-columns: 1fr; }
  .banda-interior { grid-template-columns: 1fr; gap: 32px; }
  .tubo { max-width: 160px; margin: 0 auto; }
  .pasos { grid-template-columns: 1fr; gap: 26px; }
  .pasos::before { left: 7px; right: auto; top: 0; bottom: 0; width: 1px; height: auto; }
  .pasos li { padding-top: 0; padding-left: 40px; }
  .pasos li::before { top: 2px; }
  .sede { grid-template-columns: 1fr; gap: 36px; }
}
@media (max-width: 560px) {
  .envoltura { width: calc(100% - 32px); }
  .area { min-height: 0; padding: 28px; }
  .area-cuerpo { align-items: flex-start; }
  .icono { width: 48px; height: 48px; }
  .banda-caja { padding: 28px; }
  .fila-lab { grid-template-columns: 1fr; gap: 6px; }
}
</style>
