"""Identities: list, create, change and remove the profiles a person may see or owns."""

from typing import Annotated

from fastapi import APIRouter, Depends

from docuhive import profiles
from docuhive.auth import current_user
from docuhive.contracts import CurrentUser

from .views import problem

router = APIRouter(prefix="/api/profiles", tags=["profiles"])
UserDep = Annotated[CurrentUser, Depends(current_user)]


def _missing() -> Exception:
    return problem(404, "profile_not_found", "This identity does not exist or is not yours.")


@router.get("", response_model=list[profiles.ProfileOut])
def list_profiles(user: UserDep) -> list[profiles.ProfileOut]:
    return profiles.list_for(user)


@router.post("", response_model=profiles.ProfileOut, status_code=201)
def create_profile(body: profiles.ProfileIn, user: UserDep) -> profiles.ProfileOut:
    return profiles.save(user, body)


@router.put("/{profile_id}", response_model=profiles.ProfileOut)
def update_profile(profile_id: int, body: profiles.ProfileIn, user: UserDep) -> profiles.ProfileOut:
    try:
        return profiles.save(user, body, profile_id)
    except profiles.NotFound as error:
        raise _missing() from error


@router.delete("/{profile_id}", status_code=204)
def delete_profile(profile_id: int, user: UserDep) -> None:
    try:
        profiles.delete(user, profile_id)
    except profiles.NotFound as error:
        raise _missing() from error


@router.post("/{profile_id}/test-mail")
def test_mail(profile_id: int, user: UserDep) -> dict:
    """A short mail from the identity to its own address, to check the server settings."""
    from docuhive import outgoing

    try:
        identity = profiles.get(user, profile_id)
        if identity.smtp is None or identity.owner_id != user.id:
            raise profiles.NotFound(profile_id)
        sent = outgoing.send(
            user,
            profile_id,
            [identity.smtp.from_address],
            "DocuHive test mail",
            "If you read this, DocuHive can send mail as this identity.",
            copy_to_sender=False,
            keep=False,
        )
    except profiles.NotFound as error:
        raise _missing() from error
    except outgoing.Refused as error:
        raise problem(422, "mail_refused", str(error)) from error
    return {"message": f"Sent to {', '.join(sent.recipients)}."}
