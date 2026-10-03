from dataclasses import dataclass


@dataclass
class ServiceError(Exception):
    status: int
    code: str
    message: str

    def detail(self) -> dict:
        return {"detail": {"code": self.code, "message": self.message}}
