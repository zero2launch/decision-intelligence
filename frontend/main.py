import pages.login  # noqa: F401 — registers @ui.page('/login')
import pages.signup  # noqa: F401 — registers @ui.page('/signup')
import pages.upload  # noqa: F401 — registers @ui.page('/upload')
import pages.chatbot  # noqa: F401 — registers @ui.page('/chatbot')
from nicegui import ui


@ui.page("/")
def index() -> None:
    ui.navigate.to("/signup")


ui.run(port=8080, title="Decision Intelligence")
