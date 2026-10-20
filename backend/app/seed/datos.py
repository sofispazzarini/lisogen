"""Datos de ejemplo. Los concept_id SNOMED CT fueron verificados contra un servidor de terminología
(Ontoserver, edición internacional) y los términos están traducidos al español."""

from dataclasses import dataclass
from datetime import date
from typing import Final

from app.domain.enums import RolUsuario

PASSWORD_DEMO: Final = "Demo-2026!"
DOMINIO_DEMO: Final = "lisogen-demo.com.ar"

PROVINCIAS: Final = [
    "Buenos Aires",
    "Catamarca",
    "Chaco",
    "Chubut",
    "Ciudad Autónoma de Buenos Aires",
    "Córdoba",
    "Corrientes",
    "Entre Ríos",
    "Formosa",
    "Jujuy",
    "La Pampa",
    "La Rioja",
    "Mendoza",
    "Misiones",
    "Neuquén",
    "Río Negro",
    "Salta",
    "San Juan",
    "San Luis",
    "Santa Cruz",
    "Santa Fe",
    "Santiago del Estero",
    "Tierra del Fuego, Antártida e Islas del Atlántico Sur",
    "Tucumán",
]

ESPECIALIDADES: Final = [
    "Cardiología",
    "Clínica Médica",
    "Dermatología",
    "Gastroenterología",
    "Genética Médica",
    "Hematología",
    "Nefrología",
    "Neumonología",
    "Neurología",
    "Oftalmología",
    "Pediatría",
    "Traumatología",
]

# (nombre, codigo_externo en la API de obras sociales). La cobertura % la informa la API (mock).
OBRAS_SOCIALES: Final = [
    ("Obra Social del Personal Sanitario (OSPS)", "OSPS"),
    ("Prepaga Andina", "ANDINA"),
    ("Obra Social Federal", "FEDERAL"),
]

SNOMED: Final[dict[int, str]] = {
    # Fabry
    79256006: "Acroparestesia",
    254788004: "Angioqueratoma cutáneo",
    45004005: "Hipohidrosis",
    420805002: "Córnea verticilata",
    29738008: "Proteinuria",
    21522001: "Dolor abdominal",
    60862001: "Tinnitus",
    # Pompe
    398152000: "Hipotonía",
    8186001: "Cardiomegalia",
    25273001: "Macroglosia",
    80515008: "Hepatomegalia",
    409623005: "Insuficiencia respiratoria",
    299698007: "Dificultad para alimentarse",
    26544005: "Debilidad muscular",
    # MPS 1
    254069004: "Disostosis múltiple",
    248185005: "Facies tosca",
    64634000: "Opacidad corneal",
    16294009: "Esplenomegalia",
    396347007: "Hernia umbilical",
    84445001: "Rigidez articular",
    414564002: "Cifosis",
    15188001: "Hipoacusia",
    # Gaucher
    302215000: "Trombocitopenia",
    271737000: "Anemia",
    12584003: "Dolor óseo",
    312894000: "Osteopenia",
    84229001: "Fatiga",
    # ASMD
    36760000: "Hepatoesplenomegalia",
    233703007: "Enfermedad pulmonar intersticial",
    370992007: "Dislipidemia",
    54840006: "Retraso del crecimiento",
    49473001: "Mancha rojo cereza macular",
    # Generales (para que el buscador no sólo encuentre síntomas lisosomales)
    386661006: "Fiebre",
    25064002: "Cefalea",
}

# nombre → (cardinal, secundarios, es_pompe, genes)
PATOLOGIAS: Final[dict[str, tuple[int, list[int], bool, list[str]]]] = {
    "Fabry": (79256006, [254788004, 45004005, 420805002, 29738008, 21522001, 60862001], False, ["GLA"]),
    "Pompe": (398152000, [8186001, 25273001, 80515008, 409623005, 299698007, 26544005], True, ["GAA"]),
    "MPS 1": (
        254069004,
        [248185005, 64634000, 80515008, 16294009, 396347007, 84445001, 414564002, 15188001],
        False,
        ["IDUA"],
    ),
    "Gaucher": (16294009, [80515008, 302215000, 271737000, 12584003, 312894000, 84229001], False, ["GBA1"]),
    "ASMD": (36760000, [233703007, 302215000, 370992007, 54840006, 49473001], False, ["SMPD1"]),
}

GENES_HALLAZGOS_SECUNDARIOS: Final = ["BRCA1", "BRCA2", "MLH1", "LDLR", "MYBPC3"]

# Feriados nacionales 2026 (Ley 27.399; trasladables movidos según la regla de martes/miércoles → lunes
# anterior y jueves/viernes → lunes siguiente). No incluye días no laborables ni "puentes" turísticos.
FERIADOS_2026: Final = [
    (date(2026, 1, 1), "Año Nuevo"),
    (date(2026, 2, 16), "Carnaval"),
    (date(2026, 2, 17), "Carnaval"),
    (date(2026, 3, 24), "Día Nacional de la Memoria por la Verdad y la Justicia"),
    (date(2026, 4, 2), "Día del Veterano y de los Caídos en la Guerra de Malvinas"),
    (date(2026, 4, 3), "Viernes Santo"),
    (date(2026, 5, 1), "Día del Trabajador"),
    (date(2026, 5, 25), "Día de la Revolución de Mayo"),
    (date(2026, 6, 15), "Paso a la Inmortalidad del General Martín Miguel de Güemes"),
    (date(2026, 6, 20), "Paso a la Inmortalidad del General Manuel Belgrano"),
    (date(2026, 7, 9), "Día de la Independencia"),
    (date(2026, 8, 17), "Paso a la Inmortalidad del General José de San Martín"),
    (date(2026, 10, 12), "Día del Respeto a la Diversidad Cultural"),
    (date(2026, 11, 23), "Día de la Soberanía Nacional"),
    (date(2026, 12, 8), "Inmaculada Concepción de María"),
    (date(2026, 12, 25), "Navidad"),
]

# (nombre, dirección, provincia, latitud, longitud): coordenadas reales de cada ciudad/barrio.
CENTROS: Final = [
    (
        "Centro de Extracción Palermo",
        "Av. Santa Fe 3200, CABA",
        "Ciudad Autónoma de Buenos Aires",
        "-34.588900",
        "-58.410600",
    ),
    (
        "Centro de Extracción Caballito",
        "Av. Rivadavia 5100, CABA",
        "Ciudad Autónoma de Buenos Aires",
        "-34.618600",
        "-58.442000",
    ),
    (
        "Centro de Extracción La Plata",
        "Calle 7 N° 1000, La Plata",
        "Buenos Aires",
        "-34.921400",
        "-57.954500",
    ),
    (
        "Centro de Extracción Mar del Plata",
        "Av. Colón 2500, Mar del Plata",
        "Buenos Aires",
        "-38.005500",
        "-57.542600",
    ),
    ("Centro de Extracción Córdoba Centro", "Av. Colón 600, Córdoba", "Córdoba", "-31.420100", "-64.188800"),
    ("Centro de Extracción Rosario", "Bv. Oroño 1200, Rosario", "Santa Fe", "-32.944200", "-60.650500"),
    ("Centro de Extracción Mendoza", "Av. San Martín 1100, Mendoza", "Mendoza", "-32.889500", "-68.845800"),
    (
        "Centro de Extracción Tucumán",
        "Av. Mate de Luna 1800, San Miguel de Tucumán",
        "Tucumán",
        "-26.808300",
        "-65.217600",
    ),
    ("Centro de Extracción Salta", "Av. Belgrano 900, Salta", "Salta", "-24.782100", "-65.423200"),
    ("Centro de Extracción Neuquén", "Av. Argentina 300, Neuquén", "Neuquén", "-38.951600", "-68.059100"),
]


# Un usuario por rol. Médico Tratante y Gerente Médico llevan matrícula y especialidades (E1, E29).
@dataclass(frozen=True)
class UsuarioDemo:
    rol: RolUsuario
    email: str
    nombre: str
    apellido: str
    telefono: str
    matricula: str | None = None
    especialidades: tuple[str, ...] = ()
    provincia: str | None = None


USUARIOS: Final = [
    UsuarioDemo(
        RolUsuario.MEDICO_TRATANTE,
        f"medico@{DOMINIO_DEMO}",
        "Lucía",
        "Ferreyra",
        "+54 11 4555-0101",
        matricula="MN 120345",
        especialidades=("Genética Médica", "Pediatría"),
    ),
    UsuarioDemo(RolUsuario.PACIENTE, f"paciente@{DOMINIO_DEMO}", "Martín", "Ibarra", "+54 11 4555-0102"),
    UsuarioDemo(
        RolUsuario.ADMINISTRATIVO, f"administrativo@{DOMINIO_DEMO}", "Carla", "Soria", "+54 11 4555-0103"
    ),
    UsuarioDemo(
        RolUsuario.TRANSPORTISTA,
        f"transportista@{DOMINIO_DEMO}",
        "Diego",
        "Molina",
        "+54 11 4555-0104",
        provincia="Ciudad Autónoma de Buenos Aires",
    ),
    UsuarioDemo(
        RolUsuario.BIOINFORMATICO, f"bioinformatico@{DOMINIO_DEMO}", "Ana", "Kim", "+54 11 4555-0105"
    ),
    UsuarioDemo(
        RolUsuario.GERENTE_MEDICO,
        f"gerente@{DOMINIO_DEMO}",
        "Ricardo",
        "Paz",
        "+54 11 4555-0106",
        matricula="MN 98765",
        especialidades=("Clínica Médica",),
    ),
]


@dataclass(frozen=True)
class PacienteDemo:
    dni: str
    fecha_nacimiento: date
    resumen_historia_clinica: str
    sintomas: tuple[int, ...]
    patologia: str


# Paciente demo (cuenta paciente@…): sospecha de Fabry con síntoma cardinal; particular.
PACIENTE_DEMO: Final = PacienteDemo(
    dni="30111222",
    fecha_nacimiento=date(1985, 3, 14),
    resumen_historia_clinica="Dolor urente en manos y pies desde la adolescencia, intolerancia al calor y "
    "lesiones cutáneas puntiformes en zona del traje de baño. Proteinuria leve en control reciente.",
    sintomas=(79256006, 254788004, 45004005, 29738008),
    patologia="Fabry",
)
