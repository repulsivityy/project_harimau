from enum import Enum
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
from datetime import datetime

class NodeType(str, Enum):
    IP = "ip"
    DOMAIN = "domain"
    URL = "url"
    HASH = "hash"  # File
    SENDER = "sender" # Email/Actor from context
    FILE_NAME = "file_name"
    AUTONOMOUS_SYSTEM = "asn"
    COUNTRY = "country"

class EdgeType(str, Enum):
    RESOLVES_TO = "resolves_to"        # Domain -> IP
    HOSTS = "hosts"                    # IP -> Domain (Reverse)
    COMMUNICATES_WITH = "communicates_with" # Malware -> C2
    DROPPED = "dropped"                # Malware -> Malware
    RELATED_TO = "related_to"          # Generic
    LOCATED_IN = "located_in"          # IP -> Country
    BELONGS_TO = "belongs_to"          # IP -> ASN

class GraphNode(BaseModel):
    id: str  # The unique identifier (e.g., the IP address, Hash string)
    type: NodeType
    label: str # Human readable label
    attributes: Dict[str, Any] = Field(default_factory=dict)
    
    # Metadata
    discovered_by: str = "system" # Agent name
    discovered_at: datetime = Field(default_factory=datetime.utcnow)
    score: int = 0 # 0-100 maliciousness

class GraphEdge(BaseModel):
    source: str # Node ID
    target: str # Node ID
    type: EdgeType
    attributes: Dict[str, Any] = Field(default_factory=dict)
    
    discovered_by: str = "system"
    discovered_at: datetime = Field(default_factory=datetime.utcnow)
