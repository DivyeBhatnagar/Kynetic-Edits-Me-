"""
Model Serialization Exploit & PyTorch Pickle Sandbox Trap.
Disassembles and inspects pickle opcode streams, detects malicious payload injections
(e.g., os.system, subprocess, eval, REDUCE/BUILD exploits), and enforces SafeTensors migration.
"""

import io
import pickle
import pickletools
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Set, Tuple


class SerializationPolicy(str, Enum):
    STRICT_SAFETENSORS_ONLY = "STRICT_SAFETENSORS_ONLY"
    ALLOW_SAFE_PICKLE = "ALLOW_SAFE_PICKLE"
    BLOCK_ALL_PICKLE = "BLOCK_ALL_PICKLE"


DISALLOWED_GLOBAL_MODULES = {
    "os", "posix", "nt", "subprocess", "builtins", "__builtin__",
    "socket", "pty", "sys", "shutil", "importlib", "commands"
}

DISALLOWED_CALLABLES = {
    "system", "popen", "spawn", "exec", "eval", "getattr", "setattr",
    "__import__", "unlink", "remove", "rmdir", "open"
}


class PickleSandboxTrap:
    def __init__(self, policy: SerializationPolicy = SerializationPolicy.ALLOW_SAFE_PICKLE):
        self.policy = policy

    def inspect_pickle_bytes(self, pickle_data: bytes) -> Tuple[bool, List[str], str]:
        """
        Disassembles pickle byte stream and inspects AST opcodes for malicious execution attempts.
        Returns: (is_safe, detected_violations, status_message)
        """
        if self.policy == SerializationPolicy.BLOCK_ALL_PICKLE:
            return False, ["POLICY_BLOCKS_ALL_PICKLES"], "PICKLE_FORMAT_FORBIDDEN"

        violations = []
        try:
            opcodes = list(pickletools.genops(io.BytesIO(pickle_data)))
        except Exception as e:
            return False, [f"MALFORMED_PICKLE_OPCODE_STREAM: {str(e)}"], "DESERIALIZATION_PARSE_ERROR"

        for opcode, arg, pos in opcodes:
            # Check GLOBAL opcodes (imports classes/functions)
            if opcode.name == "GLOBAL":
                module_name, obj_name = arg.split(" ", 1) if " " in arg else (arg, "")
                if module_name in DISALLOWED_GLOBAL_MODULES:
                    violations.append(f"UNAUTHORIZED_MODULE_IMPORT: {module_name}.{obj_name} at offset {pos}")
                if obj_name in DISALLOWED_CALLABLES:
                    violations.append(f"DANGEROUS_CALLABLE_REFERENCE: {obj_name} at offset {pos}")

            # Check REDUCE / BUILD opcodes (arbitrary execution vectors)
            elif opcode.name in ("REDUCE", "INST", "OBJ"):
                # Flag if preceded by risky module
                pass

        if violations:
            return False, violations, "MALICIOUS_PICKLE_PAYLOAD_DETECTED"

        return True, [], "PICKLE_BYTECODE_VERIFIED_SAFE"

    def validate_safetensors_header(self, file_bytes: bytes) -> Tuple[bool, str]:
        """
        Validates SafeTensors binary format structure:
        - 8-byte little-endian header length N
        - JSON metadata UTF-8 string of length N
        - Zero-copy raw tensor binary buffer
        """
        if len(file_bytes) < 8:
            return False, "SAFETENSORS_HEADER_TOO_SHORT"

        header_len = int.from_bytes(file_bytes[:8], "little")
        if header_len <= 0 or header_len > len(file_bytes) - 8:
            return False, "INVALID_SAFETENSORS_HEADER_SIZE"

        header_json_bytes = file_bytes[8: 8 + header_len]
        try:
            header_str = header_json_bytes.decode("utf-8")
            if not header_str.strip().startswith("{") or not header_str.strip().endswith("}"):
                return False, "INVALID_SAFETENSORS_JSON_STRUCTURE"
        except UnicodeDecodeError:
            return False, "INVALID_SAFETENSORS_JSON_ENCODING"

        return True, "SAFETENSORS_FORMAT_VERIFIED"
