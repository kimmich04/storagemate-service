from app.schemas import CamelModel


class LocationRead(CamelModel):
    id: int
    code: str
    name: str
