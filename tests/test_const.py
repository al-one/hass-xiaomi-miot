from custom_components.xiaomi_miot.core.const import UnitOfDensity, UnitOfRatio


def test_concentration_unit_compatibility():
    assert UnitOfDensity.MICROGRAMS_PER_CUBIC_METER == "μg/m³"
    assert UnitOfDensity.MILLIGRAMS_PER_CUBIC_METER == "mg/m³"
    assert UnitOfRatio.PARTS_PER_MILLION == "ppm"
