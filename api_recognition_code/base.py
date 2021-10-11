from abc import abstractmethod
from discussion.model.base import SOPost


class SOPostAPIRecognition:
    @abstractmethod
    def recognize(self, post: SOPost):
        return set()


class SOPostAPILinker:
        def link_one(self, post: SOPost, api):
        return api

    def link_batch(self, post: SOPost, api):
        return api
