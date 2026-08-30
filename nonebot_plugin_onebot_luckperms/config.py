from typing import List, Literal
from pydantic import BaseModel, Field


class OBLPConfig(BaseModel):
    oblp_store_type: Literal["memory", "sqlite", "redis"] = "sqlite"
    oblp_redis_url: str = "redis://localhost:6379/0"
    oblp_default_group_owner: List[str] = Field(
        default_factory=lambda: ["luckperms.help"]
    )
    oblp_default_group_admin: List[str] = Field(default_factory=list)
    oblp_default_group_member: List[str] = Field(default_factory=list)
    oblp_superuser_inherit: List[str] = Field(default_factory=lambda: ["luckperms.*"])
    oblp_cache_ttl: int = 300