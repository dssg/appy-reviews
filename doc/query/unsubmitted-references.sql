-- recommenders, requested, but as yet unreceived
-- (recommender email, applicant email)
(select lower(p1."Field670"), lower(p1."Field461") from survey_application_1_2020 p1 join survey_application_2_2020 p2 on (lower(p1."Field461") = lower(p2."Field461")))
union
(select lower(p1."Field673"), lower(p1."Field461") from survey_application_1_2020 p1 join survey_application_2_2020 p2 on (lower(p1."Field461") = lower(p2."Field461")))
except
(select lower("Field677"), lower("Field461") from survey_recommendation_2020);
