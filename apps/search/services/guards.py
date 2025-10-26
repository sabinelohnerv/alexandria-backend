from typing import Dict, Optional
import re


class QueryGuardException(Exception):
    """Excepción lanzada cuando una consulta no pasa los guards."""
    def __init__(self, message: str, code: str = "out_of_scope"):
        self.message = message
        self.code = code
        super().__init__(self.message)


def is_legal_query(query: str) -> bool:
    """
    Determina si una consulta tiene enfoque jurídico.
    
    Criterios:
    - Contiene términos legales clave
    - No es demasiado vaga o genérica
    - Tiene longitud mínima razonable
    
    Args:
        query: Texto de la consulta del usuario
        
    Returns:
        True si la consulta parece jurídica, False en caso contrario
    """
    if not query or len(query.strip()) < 10:
        return False
    
    query_lower = query.lower()
    
    # Términos jurídicos comunes en español
    legal_terms = [
        # Términos generales
        'ley', 'leyes', 'legal', 'jurídico', 'jurídica', 'derecho', 'derechos',
        'norma', 'normas', 'normativa', 'reglamento', 'decreto', 'resolución',
        
        # Áreas del derecho
        'penal', 'civil', 'laboral', 'comercial', 'constitucional', 'administrativo',
        'tributario', 'fiscal', 'mercantil', 'procesal', 'contractual',
        
        # Conceptos jurídicos
        'contrato', 'demanda', 'sentencia', 'juicio', 'tribunal', 'juzgado',
        'código', 'artículo', 'inciso', 'párrafo', 'disposición',
        'delito', 'sanción', 'multa', 'pena', 'condena',
        'recurso', 'apelación', 'casación', 'amparo',
        
        # Actores jurídicos
        'juez', 'fiscal', 'abogado', 'defensor', 'procurador',
        'demandante', 'demandado', 'acusado', 'imputado',
        
        # Procedimientos
        'proceso', 'procedimiento', 'trámite', 'instancia',
        'notificación', 'citación', 'audiencia', 'alegato',
        
        # Documentos
        'escritura', 'testamento', 'poder', 'acta', 'certificado',
        'licencia', 'permiso', 'autorización',
        
        # Derechos específicos
        'propiedad', 'posesión', 'usufructo', 'servidumbre',
        'patente', 'marca', 'copyright', 'autor',
        'herencia', 'sucesión', 'testamentario',
        
        # Obligaciones
        'obligación', 'responsabilidad', 'deber', 'cumplimiento',
        'incumplimiento', 'indemnización', 'daño', 'perjuicio',
        
        # Términos procesales
        'prescripción', 'caducidad', 'nulidad', 'anulación',
        'revocación', 'suspensión', 'ejecución',
        
        # Constitucional
        'constitución', 'constitucional', 'inconstitucional',
        'garantía', 'amparo', 'habeas',
        
        # Laboral
        'trabajador', 'empleador', 'contrato laboral', 'despido',
        'indemnización laboral', 'salario', 'jornada',
        
        # Familia
        'divorcio', 'matrimonio', 'custodia', 'alimentos', 'patria potestad',
        'adopción', 'filiación', 'régimen patrimonial',
        
        # Penal específico
        'homicidio', 'robo', 'hurto', 'estafa', 'fraude',
        'violación', 'abuso', 'corrupción', 'cohecho',
        
        # Tributario
        'impuesto', 'tributo', 'contribución', 'tasa',
        'exención', 'deducción', 'declaración jurada',
    ]
    
    # Verificar si contiene al menos un término legal
    has_legal_term = any(term in query_lower for term in legal_terms)
    
    # Patrones que sugieren contexto legal
    legal_patterns = [
        r'\bart[íi]culo\s+\d+',  # artículo 123
        r'\bley\s+n[°º]?\s*\d+',  # ley n° 123
        r'\bdecreto\s+\d+',  # decreto 123
        r'\bc[óo]digo\s+(civil|penal|laboral|comercial)',  # código civil
        r'\bsentencia\s+n[°º]?\s*\d+',  # sentencia n° 123
        r'\bexpediente\s+n[°º]?\s*\d+',  # expediente n° 123
    ]
    
    has_legal_pattern = any(re.search(pattern, query_lower) for pattern in legal_patterns)
    
    return has_legal_term or has_legal_pattern


def is_too_vague(query: str) -> bool:
    """
    Determina si una consulta es demasiado vaga o genérica.
    
    Args:
        query: Texto de la consulta del usuario
        
    Returns:
        True si la consulta es demasiado vaga, False en caso contrario
    """
    if not query or len(query.strip()) < 10:
        return True
    
    query_lower = query.lower().strip()
    
    # Consultas extremadamente cortas (menos de 3 palabras significativas)
    words = [w for w in query_lower.split() if len(w) > 2]
    if len(words) < 3:
        return True
    
    # Patrones de consultas vagas
    vague_patterns = [
        r'^(hola|hi|hey|buenas|buenos días|buenas tardes|buenas noches)[\s\.,!?]*$',
        r'^(ayuda|help|auxilio)[\s\.,!?]*$',
        r'^(qué|que|como|cómo|cuál|cual|cuando|cuándo|donde|dónde)[\s\.,!?]*$',
        r'^(sí|si|no|ok|vale|bien)[\s\.,!?]*$',
        r'^(gracias|thanks|thx)[\s\.,!?]*$',
        r'^(test|prueba|testing)[\s\.,!?]*$',
    ]
    
    for pattern in vague_patterns:
        if re.match(pattern, query_lower):
            return True
    
    # Consultas genéricas sin contexto
    generic_queries = [
        'qué es esto',
        'cómo funciona',
        'ayúdame',
        'necesito ayuda',
        'tengo una pregunta',
        'quiero saber',
        'dime',
        'explícame',
        'información',
    ]
    
    if query_lower in generic_queries:
        return True
    
    return False


def validate_query(query: str) -> Optional[Dict[str, str]]:
    """
    Valida una consulta antes de procesarla.
    
    Args:
        query: Texto de la consulta del usuario
        
    Returns:
        None si la consulta es válida
        Dict con 'message' y 'code' si la consulta no es válida
        
    Raises:
        QueryGuardException: Si la consulta no pasa las validaciones
    """
    if not query or not query.strip():
        raise QueryGuardException(
            "La consulta no puede estar vacía.",
            code="empty_query"
        )
    
    # Validar longitud mínima
    if len(query.strip()) < 10:
        raise QueryGuardException(
            "Este asistente responde exclusivamente consultas jurídicas. "
            "Por favor, formula tu pregunta con enfoque legal.",
            code="too_short"
        )
    
    # Validar que no sea demasiado vaga
    if is_too_vague(query):
        raise QueryGuardException(
            "Este asistente responde exclusivamente consultas jurídicas. "
            "Por favor, formula tu pregunta con enfoque legal.",
            code="too_vague"
        )
    
    # Validar que sea una consulta jurídica
    if not is_legal_query(query):
        raise QueryGuardException(
            "Este asistente responde exclusivamente consultas jurídicas. "
            "Por favor, formula tu pregunta con enfoque legal.",
            code="not_legal"
        )
    
    return None


def check_query_guards(query: str) -> None:
    """
    Verifica los guards de la consulta y lanza excepción si no pasa.
    
    Args:
        query: Texto de la consulta del usuario
        
    Raises:
        QueryGuardException: Si la consulta no pasa las validaciones
    """
    validate_query(query)
