# Generated by Django 2.0 on 2018-01-31 05:00
import enum
import itertools
import operator

from django.db import migrations


RATINGS1 = (-1, -1, 0, 1, 2)


class Label(str, enum.Enum):

    programming = "Programming Ability"
    machine_learning = "Stats/Machine Learning Ability"
    data_handling = "Data Handling/Manipulation Skills"
    interest_in_good = "Interest in Social Good"
    communication = "Communication Ability"
    teamwork = "Would this person work well in a team?"
    overall = "Overall Recommendation"

    def __str__(self):
        return self.value


class OverallRecommendation(str, enum.Enum):

    accept = "Accept"
    reject = "Reject"
    only_if = "Only if you need a certain type of fellow (explain below)"

    def __str__(self):
        return self.value


def copy_ratings_to_reviews(apps, schema_editor):
    Rating = apps.get_model('review', 'Rating')

    ratings = Rating.objects.select_related().order_by('review')
    for (review, review_ratings) in itertools.groupby(ratings.iterator(),
                                                      operator.attrgetter('review')):
        review_scores = {
            review_rating.label: review_rating.score
            for review_rating in review_ratings
        }

        for label in Label:
            if label.name in review_scores:
                review_score = review_scores[label.name]

                if label is Label.overall:
                    review.overall_recommendation = (
                        OverallRecommendation.accept.name if review_score > 3 else
                        OverallRecommendation.reject.name
                    )
                else:
                    setattr(review, f'{label.name}_rating', RATINGS1[review_score - 1])

        review.save()


class Migration(migrations.Migration):

    dependencies = [
        ('review', '0004_auto_20180131_0457'),
    ]

    operations = [
        migrations.RunPython(copy_ratings_to_reviews),
    ]
