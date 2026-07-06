from typing import List, Literal
from pydantic import BaseModel, Field, ConfigDict


class OBLPConfig(BaseModel):
    model_config = ConfigDict(env_prefix="OBLP_", extra="ignore")

    store_type: Literal["memory", "sqlite", "redis"] = "sqlite"
    sqlite_path: str = "./data/oblp/permissions.db"
    redis_url: str = "redis://localhost:6379/0"
    default_group_owner: List[str] = Field(default_factory=lambda: ["luckperms.help"])
    default_group_admin: List[str] = Field(default_factory=list)
    default_group_member: List[str] = Field(default_factory=list)
    superuser_inherit: List[str] = Field(default_factory=lambda: ["luckperms.*"])
    cache_ttl: int = 300
    debug_mode: bool = False
    message_file: str = "./data/oblp/messages.yml"


oblp_config = OBLPConfig()
