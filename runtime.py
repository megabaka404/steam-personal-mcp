from __future__ import annotations

from dataclasses import dataclass

from cache.memory_cache import MemoryTTLCache
from clients.mock_clients import MockSteamClient, MockStoreClient
from clients.steam_client import SteamClient
from clients.store_client import StoreClient
from config import Settings
from resolver.game_resolver import GameResolver
from services.activity_service import ActivityService
from services.achievement_service import AchievementService
from services.friend_service import FriendService
from services.library_service import LibraryService
from services.recommendation_service import RecommendationService
from services.store_service import StoreService
from services.store_recommendation_service import StoreRecommendationService
from services.price_history_service import PriceHistoryService
from services.p1_service import P1Service
from services.p2_service import P2Service
from services.game_intel_service import GameIntelService
from services.local_steam_service import LocalSteamService
from price_history import PriceHistoryStore
from activity_history import ActivityHistoryStore
from game_history import GameObservationStore


@dataclass
class Runtime:
    settings: Settings
    cache: MemoryTTLCache
    steam: object
    store_client: object
    library: LibraryService
    resolver: GameResolver
    achievements: AchievementService
    store: StoreService
    friends: FriendService
    recommendations: RecommendationService
    activity: ActivityService
    price_history: PriceHistoryStore
    price_history_service: PriceHistoryService
    store_recommendations: StoreRecommendationService
    p1: P1Service
    activity_history: ActivityHistoryStore
    p2: P2Service
    game_history: GameObservationStore
    local_steam: LocalSteamService
    game_intel: GameIntelService

    def close(self) -> None:
        for client in (self.steam, self.store_client):
            http = getattr(client, "http", None)
            if http is not None and hasattr(http, "close"):
                http.close()
        self.price_history.close()
        self.activity_history.close()
        self.game_history.close()


def build_runtime(settings: Settings) -> Runtime:
    cache = MemoryTTLCache()
    if settings.mock:
        steam = MockSteamClient()
        store_client = MockStoreClient()
    else:
        steam = SteamClient(settings, cache)
        store_client = StoreClient(settings, cache)
    library = LibraryService(steam, cache, settings)
    resolver = GameResolver(lambda: [game.model_dump() for game in library.owned_games()], store_client.search)
    library.resolver = resolver
    achievements = AchievementService(steam, library, resolver)
    price_history = PriceHistoryStore(settings.history_db_path)
    store = StoreService(store_client, steam, library, resolver, settings, price_history=price_history)
    friends = FriendService(steam, library)
    recommendations = RecommendationService(library, achievements)
    store_recommendations = StoreRecommendationService(store_client, store, library, steam, resolver)
    price_history_service = PriceHistoryService(store, price_history)
    p1 = P1Service(store_client, store, store_recommendations, library, steam, price_history, settings)
    activity_history = ActivityHistoryStore(settings.history_db_path)
    activity = ActivityService(steam, library, achievements, store, settings, activity_history=activity_history)
    p2 = P2Service(activity_history, library)
    game_history = GameObservationStore(settings.history_db_path)
    local_steam = LocalSteamService(store=store_client)
    game_intel = GameIntelService(
        store_client=store_client,
        store_service=store,
        steam=steam,
        library=library,
        resolver=resolver,
        achievements=achievements,
        price_history=price_history,
        game_history=game_history,
        local_steam=local_steam,
    )
    return Runtime(settings, cache, steam, store_client, library, resolver, achievements, store, friends, recommendations, activity, price_history, price_history_service, store_recommendations, p1, activity_history, p2, game_history, local_steam, game_intel)
