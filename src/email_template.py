from jinja2 import Template


SUBJECT_TEMPLATE = Template("CougarCS x {{company}} - Partnership Opportunity")

EMAIL_TEMPLATE = Template("""
Hi {{first_name}},

I hope this email finds you well! My name is {{officer}}, and I'm the {{role}} for the University of Houston's largest Computer Science student organization, CougarCS.

CougarCS is an ACM chapter organization committed to the professional development and academic success of our 200+ active members. We provide various services to our students, including company-sponsored career readiness workshops, personalized tutoring sessions, and a wide library of open-source projects built and maintained by our members. We've worked with companies such as Google, Microsoft, and Apple, and have partnered with over 50 companies to bring exciting events for our members. Additionally, we host CodeRED, the largest hackathon at UH.

As a sponsor, {{company}} will have access to several CougarCS perks, such as candid facetime with experienced student developers, extensive brand recognition marketing through our social media platforms, and a live environment where users can test your product and provide direct feedback. {{company}} can expect no less than a multitude of recruitment and marketing opportunities from our team!

I would love to set up a quick chat to discuss a potential partnership between CougarCS and {{company}}. If you would like to learn more about our organization, please refer to our website:
      
cougarcs.com

Thank you for your time! We look forward to hearing from you soon.

Best regards,
{{officer}}, {{role}}
""")

def email_creator(contact_first_name, company, officer_name, officer_role):
  subject = SUBJECT_TEMPLATE.render(
    company=company
  )

  body = EMAIL_TEMPLATE.render(
    first_name=contact_first_name,
    officer=officer_name,
    role=officer_role,
    company=company
  )

  return subject, body