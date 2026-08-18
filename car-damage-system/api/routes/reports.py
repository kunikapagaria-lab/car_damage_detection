"""FastAPI router that re-exports the PDF report endpoint.

Mount this router in main.py:
    from api.routes.reports import router as reports_router
    app.include_router(reports_router)
"""

from reports.pdf_generator import router  # re-export

__all__ = ["router"]
