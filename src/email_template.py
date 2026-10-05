from jinja2 import Template


SUBJECT_TEMPLATE = Template("CougarCS x {{company}} - Partnership Opportunity")

EMAIL_TEMPLATE = Template("""
<html>
  <body>
    <p>Dear {{first_name}} {{last_name}},</p>

    <p>
      I hope this email finds you well! My name is {{officer}}, and I'm the {{role}} for
      the University of Houston's largest Computer Science student organization, CougarCS.
      CougarCS is an ACM chapter organization with 200+ active members, and we're committed
      to the professional and academic success of our students through company-sponsored
      events, tailor-made tutoring workshops, and CodeRED, the University of Houston's largest
      hackathon experience.
    </p>
                          
    <p>
      As a first generation university student, I've experienced the challenges that underrepresented groups face
      in breaking into the tech industry. Navigating these challenges and becoming a leader in the Computer Science
      community through CougarCS has provided me the opportunity to platform students from various backgrounds and empower
      them with the tools and connections necessary to break into the industry.
    </p>
                          
    <p>
      As a sponsor, {{company}} can assist in our mission to further democratize our industry and inspire the next
      generation of multicultural tech talent!
    </p>
                          
    <p>
      We would love to host an event with your company on the University of Houston campus, where you can present new programs
      and initiatives, share opportunities in your company, and get candid facetime with our student members.
    </p>

    <p>
      If you are interested, we can set up a quick chat to discuss potential next steps with CougarCS and
      {{company}}.
    </p>


    <p>Thank you for your time! We look forward to hearing from you soon.</p>
                          
    <p>Best,</p>
    {{signature_html | safe}}
  </body>
</html>
""")

MIXER_SUBJECT_TEMPLATE = Template("CodeRED x {{company}} - Career Mixer Invite")

MIXER_EMAIL_TEMPLATE = Template("""
<html>
  <body>
    <p>Hi {{first_name}} {{last_name}},</p>

    <p>
      I hope this email finds you well! My name is {{officer}}, and I'm the {{role}} for
      the University of Houston's largest Computer Science student organization, CougarCS.
    </p>

    <p>
      I'm emailing you today because we want to formally invite {{company}} to CodeRED's career
      mixer! This networking event gives {{company}} an opportunity to connect with
      industry-ready tech students and gain a recruiting foothold on the University of Houston campus.
    </p>

    <p>
      The mixer will take place on October 10th from 9:00 AM to 11:30 AM, and our amenities will
      include shirts, plushies, and food! Let us know if you are interested, and we can send over
      more details about the event.
    </p>

    <p>We hope to see you there!</p>

    <p>Best,</p>
    {{signature_html | safe}}
  </body>
</html>
""")


def email_creator(
  contact_first_name,
  contact_last_name,
  company,
  officer_name,
  officer_role,
  signature_html=""
):
  subject = SUBJECT_TEMPLATE.render(
    company=company
  )

  body = EMAIL_TEMPLATE.render(
    first_name=contact_first_name,
    last_name=contact_last_name,
    officer=officer_name,
    role=officer_role,
    company=company,
    signature_html=signature_html,
  )

  return subject, body

def mixer_email_creator(
  contact_first_name,
  contact_last_name,
  company,
  officer_name,
  officer_role,
  signature_html="" 
):
  subject = MIXER_SUBJECT_TEMPLATE.render(
    company=company
  )

  body = MIXER_EMAIL_TEMPLATE.render(
    first_name=contact_first_name,
    last_name=contact_last_name,
    officer=officer_name,
    role=officer_role,
    company=company,
    signature_html=signature_html,
  )

  return subject, body 