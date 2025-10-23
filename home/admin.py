from django.contrib import admin
from django import forms
from .models import KioskClient, KioskConfiguration, KioskHealthCheck, Order, CardImage, KioskDevice, ReaderDevice
from django.core.files.base import ContentFile
import csv
import io

class KioskConfigurationInline(admin.StackedInline):
    model = KioskConfiguration
    can_delete = False
    verbose_name_plural = 'Configuration'
    classes = ['collapsee']  # Makes it collapsible in Black theme
    fieldsets = (
        ('Location', {
            'fields': ('location_name',),
            'classes': ['collapsee show']  # Black theme styling
        }),
        ('Display Settings', {
            'fields': ('theme', 'custom_header'),
            'classes': ['collapsee show']
        }),
        ('Functionality', {
            'fields': ('idle_timeout_seconds', 'allow_printer', 'maintenance_mode'),
            'classes': ['collapsee show']
        })
    )

class KioskClientForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput, required=False, help_text='Leave empty to keep current password')
    
    class Meta:
        model = KioskClient
        fields = ('login_name', 'password', 'is_active')

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.cleaned_data.get('password'):
            instance.set_password(self.cleaned_data['password'])
        if commit:
            instance.save()
        return instance

# @admin.register(KioskDevice)
# class KioskDeviceAdmin(admin.ModelAdmin):
#     list_display = ("kiosk_id", "status", "location", "registered_at", "last_seen_at")
#     search_fields = ("kiosk_id", "location")
#     list_filter = ("status",)

# @admin.register(ReaderDevice)
# class ReaderDeviceAdmin(admin.ModelAdmin):
#     list_display = ("reader_id", "name", "country", "city", "state", "address", "postalCode", "kiosk", "registered_at")
#     search_fields = ("reader_id", "name")
#     list_filter = ("kiosk",)
@admin.register(KioskClient)
class KioskClientAdmin(admin.ModelAdmin):
    form = KioskClientForm
    inlines = [KioskConfigurationInline]
    list_display = ('login_name', 'is_active', 'location', 'last_login', 'created_at')
    list_filter = ('is_active', 'configuration__maintenance_mode', 'configuration__theme')
    search_fields = ('login_name', 'configuration__location_name')
    readonly_fields = ('id', 'last_login', 'created_at', 'updated_at')
    
    def location(self, obj):
        return obj.configuration.location_name if hasattr(obj, 'configuration') else '-'
    location.short_description = 'Location'

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        # Create default configuration if it doesn't exist
        if not hasattr(obj, 'configuration'):
            KioskConfiguration.objects.create(kiosk=obj)
        # Create health check entry if it doesn't exist
        if not hasattr(obj, 'health_check'):
            KioskHealthCheck.objects.create(kiosk=obj)

    fieldsets = (
        ('Kiosk Details', {
            'fields': ('id', 'login_name', 'password', 'is_active'),
            'classes': ['collapsee show']  # Black theme styling
        }),
        ('Timestamps', {
            'fields': ('last_login', 'created_at', 'updated_at'),
            'classes': ['collapsee']
        }),
    )

@admin.register(KioskConfiguration)
class KioskConfigurationAdmin(admin.ModelAdmin):
    list_display = ('kiosk', 'location_name', 'theme', 'maintenance_mode', 'allow_printer')
    list_filter = ('theme', 'maintenance_mode', 'allow_printer')
    search_fields = ('location_name', 'kiosk__login_name')
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        ('Kiosk Association', {
            'fields': ('kiosk',),
            'classes': ['collapsee show']  # Black theme styling
        }),
        ('Location', {
            'fields': ('location_name',),
            'classes': ['collapsee show']
        }),
        ('Display Settings', {
            'fields': ('theme', 'custom_header'),
            'classes': ['collapsee show']
        }),
        ('Functionality', {
            'fields': ('idle_timeout_seconds', 'allow_printer', 'maintenance_mode'),
            'classes': ['collapsee show']
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ['collapsee']
        }),
    )

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('transaction_id', 'kiosk_id', 'price', 'num_pictures', 'status', 'created_at', 'updated_at')
    search_fields = ('transaction_id', 'kiosk_id')
    list_filter = ('status', 'created_at')
    ordering = ('-created_at', 'status')

@admin.register(CardImage)
class CardImageAdmin(admin.ModelAdmin):
    list_display = ('id', 'version', 'is_enabled', 'created_at', 'updated_at')
    list_filter = ('is_enabled',)
    readonly_fields = ('id', 'version', 'created_at', 'updated_at')
    
    actions = ['bulk_upload_images']

    def bulk_upload_images(self, request, queryset):
        if 'apply' in request.POST:
            csv_file = request.FILES.get('csv_file')
            if csv_file:
                decoded_file = csv_file.read().decode('utf-8')
                csv_data = csv.DictReader(io.StringIO(decoded_file))
                for row in csv_data:
                    if 'image_path' in row:
                        CardImage.objects.create(
                            image=row['image_path'],
                            is_enabled=row.get('is_enabled', 'True').lower() == 'true'
                        )
                self.message_user(request, "Successfully imported card images")
                return
            
        return render(
            request,
            'admin/bulk_upload_form.html',
            context={'cards': queryset}
        )
    
    bulk_upload_images.short_description = "Bulk upload images"

# Customize the admin site header and title
admin.site.site_header = 'Kiosk Management System'
admin.site.site_title = 'Kiosk Management'
admin.site.index_title = 'Kiosk Administration'
