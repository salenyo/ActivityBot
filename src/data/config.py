from __future__ import annotations

from hydra_shared.core_client import GuildConfig


class ActivityConfig(GuildConfig):
    activity_tracked_category_id: int | None = None
    activity_excluded_channel_ids: list[int] = []
    activity_contest_role_ids: list[int] = []
    activity_results_channel_id: int | None = None
    activity_contest_banner_path: str | None = None
