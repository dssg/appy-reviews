-- applicants with completed applications but less than two distinct submitted letters of reference
select lower(p1."Field461") as "applicant email"
from survey_application_1_2020 p1
join survey_application_2_2020 p2 on (lower(p1."Field461") = lower(p2."Field461"))
left outer join survey_recommendation_2020 rec on (lower(p1."Field461") = lower(rec."Field461"))
group by 1
having count(distinct lower(rec."Field677")) < 2;
