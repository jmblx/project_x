from dishka import FromDishka
from dishka.integrations.fastapi import DishkaRoute
from fastapi import APIRouter
from fastapi.responses import ORJSONResponse
from starlette.status import HTTP_200_OK

from application.investments.queries import InvestmentsQueryHandler
from application.user.notification_query_handler import NotificationQueryHandler

inv_router = APIRouter(route_class=DishkaRoute, tags=["investments"])


@inv_router.get("/investments")
async def get_all_investments(
    inv_query: FromDishka[InvestmentsQueryHandler],
) -> ORJSONResponse:
    investments = await inv_query.handle()
    return ORJSONResponse(investments, status_code=HTTP_200_OK)


@inv_router.get("/investments/notifications")
async def get_all_investments_notifications(handler: FromDishka[NotificationQueryHandler]) -> ORJSONResponse:
    notifications = await handler.handle()
    return ORJSONResponse({"notifications": notifications}, status_code=HTTP_200_OK)
