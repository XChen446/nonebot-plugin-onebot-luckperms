from typing import List, Literal
from pydantic import BaseModel, Field


class OBLPConfig(BaseModel):
    store_type: Literal["memory", "sqlite", "redis"] = "sqlite"
    redis_url: str = "redis://localhost:6379/0"
    default_group_owner: List[str] = Field(default_factory=lambda: ["luckperms.help"])
    default_group_admin: List[str] = Field(default_factory=list)
    default_group_member: List[str] = Field(default_factory=list)
    superuser_inherit: List[str] = Field(default_factory=lambda: ["luckperms.*"])
    cache_ttl: int = 300
