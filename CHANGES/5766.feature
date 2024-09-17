Introduced new immutable resource identifier: Pulp Resource Name (PRN). All objects within Pulp
will now show their PRN alongside their pulp_href. The PRN can be used in lieu of the pulp_href
in API calls when creating or filtering objects. The PRN of any object has the form of
`prn:app_label.model_label:pulp_id`.
