"""Non-probing model capability checks using metadata already supplied by PI."""


def image_model_support(adapter, model=None):
    if getattr(adapter, 'adapter_id', None) != 'pi':
        return None
    selected = model if model is not None else getattr(adapter, 'default_model', None)
    inputs = getattr(adapter, 'model_inputs', {})
    if selected is None or selected not in inputs:
        return None
    return 'image' in inputs[selected]


def require_image_model(adapter, model=None):
    if image_model_support(adapter, model) is False:
        from core.errors import HubError
        raise HubError('AGENT_IMAGE_UNSUPPORTED', '所选 PI 模型不支持图片输入，请选择支持图片的模型')
