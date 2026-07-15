from tests.fixtures.afsk1200_samples import load_afsk1200_sample


def test_load_afsk1200_sample_returns_audio_and_oracle_packets():
    sample = load_afsk1200_sample()

    assert sample.audio_ogg.startswith(b"OggS")
    assert sample.sample_rate_hint_hz == 22050
    assert len(sample.packets) == 8
    assert all(p.source == "JF6BCC-0" and p.payload == "CQ PM53 402103" for p in sample.packets)
    assert sample.provenance["norad_id"] == 25544
