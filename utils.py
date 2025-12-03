# -*- coding: utf-8 -*-
"""
Módulo de Utilitários
Funções auxiliares compartilhadas entre módulos
"""

import numpy as np

def convert_numpy_types(obj):
    """
    Converte recursivamente tipos numpy para tipos nativos do Python
    para garantir compatibilidade com JSON serialization.
    
    Args:
        obj: Objeto a ser convertido (dict, list, tuple, numpy types, etc.)
        
    Returns:
        Objeto com tipos nativos do Python
    """
    if isinstance(obj, dict):
        return {key: convert_numpy_types(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [convert_numpy_types(item) for item in obj]
    elif isinstance(obj, tuple):
        return tuple(convert_numpy_types(item) for item in obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, np.bool_):
        return bool(obj)
    elif isinstance(obj, (np.int_, np.intc, np.intp, np.int8, np.int16, np.int32, np.int64)):
        return int(obj)
    elif isinstance(obj, (np.float_, np.float16, np.float32, np.float64)):
        return float(obj)
    elif isinstance(obj, np.complex_):
        return complex(obj)
    else:
        return obj
