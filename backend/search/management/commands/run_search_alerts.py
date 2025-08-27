from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta

from search.models import SavedSearch
from search.services import SavedSearchService
from notifications.services import notify


class Command(BaseCommand):
    help = 'Run saved search alerts and send notifications for new matches'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be done without actually sending notifications',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        
        # Get all saved searches with alerts enabled
        saved_searches = SavedSearch.objects.filter(
            alerts_enabled=True
        ).select_related('user')
        
        total_processed = 0
        total_notifications = 0
        
        for saved_search in saved_searches:
            self.stdout.write(f"Processing saved search: {saved_search.name} for {saved_search.user.username}")
            
            try:
                # Get new matches since last run
                new_matches = SavedSearchService.get_new_matches_since_last_run(saved_search)
                
                if new_matches:
                    self.stdout.write(f"  Found {len(new_matches)} new matches")
                    
                    if not dry_run:
                        # Create notification
                        message = f"Your saved search '{saved_search.name}' has {len(new_matches)} new matches!"
                        
                        notify(
                            user=saved_search.user,
                            verb="search_alert",
                            message=message,
                            url=f"/search?saved_search_id={saved_search.id}",
                            metadata={
                                "saved_search_id": saved_search.id,
                                "new_matches_count": len(new_matches),
                                "listing_ids": [listing.id for listing in new_matches[:10]]  # First 10 IDs
                            }
                        )
                        
                        # Update last run time
                        saved_search.last_run_at = timezone.now()
                        saved_search.save(update_fields=['last_run_at'])
                        
                        total_notifications += 1
                    else:
                        self.stdout.write(f"  [DRY RUN] Would send notification to {saved_search.user.username}")
                else:
                    self.stdout.write("  No new matches found")
                
                total_processed += 1
                
            except Exception as e:
                self.stderr.write(f"Error processing saved search {saved_search.id}: {str(e)}")
        
        if dry_run:
            self.stdout.write(
                self.style.SUCCESS(
                    f"[DRY RUN] Processed {total_processed} saved searches, "
                    f"would have sent {total_notifications} notifications"
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Successfully processed {total_processed} saved searches, "
                    f"sent {total_notifications} notifications"
                )
            )