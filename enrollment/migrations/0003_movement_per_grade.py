from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("enrollment", "0002_sf4movemententry"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="sf4movemententry",
            name="one_movement_entry_per_category",
        ),
        migrations.AddField(
            model_name="sf4movemententry",
            name="level",
            field=models.CharField(
                max_length=20,
                choices=[
                    ("kinder", "Kinder"),
                    ("g1", "Grade 1"),
                    ("g2", "Grade 2"),
                    ("g3", "Grade 3"),
                    ("g4", "Grade 4"),
                    ("g5", "Grade 5"),
                    ("g6", "Grade 6"),
                    ("sned_es", "SNED (Non-Graded ES)"),
                    ("g7", "Grade 7"),
                    ("g8", "Grade 8"),
                    ("g9", "Grade 9"),
                    ("g10", "Grade 10"),
                    ("sned_jhs", "SNED (Non-Graded ES)"),
                    ("g11_acad", "Grade 11 ACAD"),
                    ("g11_tvl", "Grade 11 TVL"),
                    ("g11_sports", "Grade 11 SPORTS"),
                    ("g12_acad", "Grade 12 ACAD"),
                    ("g12_tvl", "Grade 12 TVL"),
                    ("g12_sports", "Grade 12 SPORTS"),
                    (
                        "legacy_total",
                        "Legacy total — needs grade allocation",
                    ),
                ],
                default="legacy_total",
            ),
            preserve_default=False,
        ),
        migrations.AddConstraint(
            model_name="sf4movemententry",
            constraint=models.UniqueConstraint(
                fields=("record", "level", "category"),
                name="one_movement_entry_per_level_category",
            ),
        ),
    ]
