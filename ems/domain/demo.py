"""Read static fixtures, validate and round-trip them; no simulated polling."""
from .models import Site, Device, TagDefinition, TelemetryEnvelope, SystemSnapshot
from .base import require


def demo_contracts(root):
    examples = root / 'contracts/examples'
    def read(cls, name):
        obj = cls.from_json((examples / (name + '.json')).read_text(encoding='utf-8'))
        require(cls.from_json(obj.to_json()) == obj, name, 'JSON round-trip mismatch')
        return obj
    site = read(Site, 'site')
    device = read(Device, 'device')
    tag = read(TagDefinition, 'soc_tag')
    require(site.id == device.site_id == tag.site_id and device.id == tag.device_id,
            'examples', 'site/device/tag mismatch')
    good = read(TelemetryEnvelope, 'telemetry_good').payload.validate_against(tag)
    offline = read(TelemetryEnvelope, 'telemetry_offline').payload.validate_against(tag)
    snapshot = read(SystemSnapshot, 'snapshot')
    require(good.value == offline.value == 60 and good.timestamp == offline.timestamp,
            'offline', 'old value must preserve measurement time')
    require(good.quality.value == 'GOOD' and offline.quality.value == 'OFFLINE'
            and offline.quality_timestamp > good.quality_timestamp
            and offline.sequence > good.sequence, 'quality', 'invalid demonstration transition')
    return {'result': 'PASS', 'stage': 'M0.1.2', 'source': 'static JSON fixtures',
            'good': good.to_dict(), 'offline': offline.to_dict(),
            'sampleTimestampPreserved': True, 'snapshotControlEligible': snapshot.control_eligible,
            'explanation': 'SOC 60% 是同一次历史测量。OFFLINE 更新质量判断时间，不把旧值变成新测量；此时不能据它控制设备。'}
