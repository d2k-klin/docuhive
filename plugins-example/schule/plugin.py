"""Tags every school letter `school`, once the AI has recognised it as one."""

from docuhive.sdk import Registry, documents


def setup(registry: Registry) -> None:
    @registry.on("document.classified")
    def tag_school_letters(event) -> None:
        if event.document_type == "school_letter":
            documents.apply_metadata(event.document_id, tags_add=["school"])
