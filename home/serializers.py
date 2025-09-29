from rest_framework import serializers

from core import settings
from .models import CardImage

class CardImageSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = CardImage
        fields = ['id', 'image_url', 'version']

    def get_image_url(self, obj):
        request = self.context.get('request')
        # if obj.image and hasattr(obj.image, 'url'):
        #     return request.build_absolute_uri(obj.image.url)

        if obj.image:
            return request.build_absolute_uri(f'{settings.MEDIA_URL}{obj.image}')
        return None 