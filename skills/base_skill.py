from abc import ABC, abstractmethod


class BaseSkill(ABC):
    def __init__(self, config: dict):
        self.config = config

    @property
    @abstractmethod
    def skill_name(self) -> str:
        pass

    @property
    @abstractmethod
    def skill_description(self) -> str:
        pass

    @abstractmethod
    async def execute(self, instruction: str) -> str:
        pass
