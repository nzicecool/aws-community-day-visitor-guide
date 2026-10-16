from speaker_profiles import SpeakerDirectory


def test_explicit_speaker_context_uses_official_bio_and_verified_linkedin():
    directory = SpeakerDirectory()
    context = directory.context_for_model("Tell me about Dmytro Sirant")
    assert "Official event biography" in context
    assert "Verified LinkedIn profile: https://www.linkedin.com/in/dmytro-sirant" in context


def test_unverified_speaker_is_not_assigned_a_linkedin_profile():
    directory = SpeakerDirectory()
    context = directory.context_for_model("Tell me about Sagar Utekar")
    assert "Official event biography" in context
    assert "Verified public LinkedIn profile: unavailable; do not guess one." in context


def test_unnamed_query_does_not_load_full_biographies():
    directory = SpeakerDirectory()
    context = directory.context_for_model("What is on at 10:30?")
    assert "Published speakers and titles" in context
    assert "No speaker biography is included" in context
